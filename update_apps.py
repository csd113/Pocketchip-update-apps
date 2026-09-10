#!/usr/bin/env python3
"""Small, dependency-free PocketCHIP app updater (Python 3 + Tk)."""
import ast
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import signal
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk
from urllib.request import Request, urlopen

VERSION = '1.5.3'
HOME = Path.home()
DATA = HOME / '.local/share/pocket-update-apps'
# Explicit trusted catalog; the updater uses a complete verified bundle.
SELF_FILES = ('update_apps.py', 'deployment.py', 'launch', 'update-apps.png',
              'bitcoin-launch', 'bitcoin.png', 'test_update_apps.py',
              'test_deployment.py', 'test_self_update.py', 'check_layout.py', 'README.md')
APPS = [dict(name='Bitcoin CAD', repo='csd113/PocketChip-Bitcoin-Display',
             branch='main', source='bitcoin.py',
             path=HOME / '.local/share/pocket-bitcoin/bitcoin.py',
             known={'14d91cc19782ced7716132a0563161bdb8cd9b86c3ceffb8053ee9409b158ccd':
                    'cd1f1d7a2a5fed4c4441abcb78c1c924fb4b6f16'}),
        dict(name='App Updater (self)', repo='csd113/Pocketchip-update-apps',
             branch='main', source='update_apps.py', path=DATA / 'update_apps.py',
             known={}, self_update=True)]
LIMIT = 2 * 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git_sha(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def revision(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{40}', value):
        raise ValueError('Invalid revision from GitHub')
    return value


def api(path):
    request = Request('https://api.github.com/repos/' + path,
                      headers={'User-Agent': 'PocketCHIP-Update-Apps/1.0',
                               'Accept': 'application/vnd.github+json'})
    with urlopen(request, timeout=20) as response:
        raw = response.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError('GitHub response is too large')
    return json.loads(raw)


def current(app):
    path = app['path']
    if any(parent.is_symlink() for parent in path.parents):
        raise ValueError('Installed app parent must not be a symlink')
    if not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink() or not path.is_file():
        raise ValueError('Installed app must be a regular file')
    if path.stat().st_size > LIMIT:
        raise ValueError('Installed app is too large')
    return path.read_bytes()


def source_version(data):
    """Read a literal version without importing or executing downloaded code."""
    tree = ast.parse(data)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == 'VERSION'
                for target in node.targets):
            value = ast.literal_eval(node.value)
            if not isinstance(value, str) or not re.fullmatch(
                    r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', value):
                raise ValueError('App VERSION must be MAJOR.MINOR.PATCH')
            return 'v' + value
    return None


def incomplete(app):
    """Detect interrupted Bitcoin installs and missing launcher support files."""
    root = app['path'].parent
    marker = root / '.installation-pending'
    if marker.is_symlink() or marker.exists():
        return True
    if current(app) is None:
        return False
    from deployment import safe
    for name in ('launch', 'bitcoin.png'):
        path = root / name
        safe(path)
        if not path.is_file() or (name == 'launch' and not os.access(path, os.X_OK)):
            return True
    return False


def installed(app):
    if not app.get('self_update') and incomplete(app):
        return 'incomplete / repair'
    data = current(app)
    if data is None:
        return 'not installed'
    version = source_version(data)
    if version:
        return version
    digest = sha(data)
    known = app['known'].get(digest)
    if known:
        return known[:8]
    try:
        receipt = json.loads((DATA / 'receipts' / (digest + '.json')).read_text())
        if receipt['repo'] == app['repo']:
            return revision(receipt['commit'])[:8]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return 'local / unknown'


def check_self(app):
    commit = revision(api(app['repo'] + '/commits/' + app['branch'])['sha'])
    tree = api(app['repo'] + '/git/trees/' + commit)
    if tree.get('truncated'):
        raise ValueError('Incomplete GitHub file list')
    entries = {entry['path']: entry for entry in tree['tree']}
    files, previous = {}, {}
    for name in SELF_FILES:
        entry = entries.get(name, {})
        if entry.get('type') != 'blob' or entry.get('mode') not in ('100644', '100755'):
            raise ValueError('Missing or unsafe updater file: ' + name)
        request = Request('https://raw.githubusercontent.com/' + app['repo'] +
                          '/' + commit + '/' + name,
                          headers={'User-Agent': 'PocketCHIP-Update-Apps'})
        with urlopen(request, timeout=20) as response:
            data = response.read(LIMIT + 1)
        if not data or len(data) > LIMIT or len(data) != entry['size']:
            raise ValueError('Invalid download size: ' + name)
        if git_sha(data) != revision(entry['sha']):
            raise ValueError('Download checksum failed: ' + name)
        if name.endswith('.py'):
            compile(data, name, 'exec')
        files[name] = (data, 0o755 if name.endswith('launch') else 0o644)
        old = current(dict(path=app['path'].parent / name))
        previous[name] = sha(old) if old is not None else None
    data = files[app['source']][0]
    return dict(commit=commit, version=source_version(data) or commit[:8],
                files=files, previous=previous,
                needed=any(sha(value[0]) != previous[name] for name, value in files.items()))


def install_self(app, result):
    # Python keeps this program in memory while files are replaced on disk.
    # Import the helper now; no new module is loaded after replacement.
    # The UI exits after success, so the next launch loads the complete new bundle.
    from deployment import safe
    files = result['files']
    if set(files) != set(SELF_FILES) or set(result['previous']) != set(SELF_FILES):
        raise ValueError('Incomplete updater bundle')
    target = app['path'].parent
    previous = {}
    for name, (data, mode) in files.items():
        path = target / name
        safe(path)
        old = current(dict(path=path))
        if (sha(old) if old is not None else None) != result['previous'][name]:
            raise ValueError('Updater changed. Check for updates again.')
        if name.endswith('.py'):
            compile(data, name, 'exec')
        previous[name] = (old, path.stat().st_mode & 0o777) if old is not None else None
    backup = Path(tempfile.mkdtemp(prefix='before-self-update-', dir=target))
    for name, old in previous.items():
        if old is not None:
            atomic(backup / name, *old)
    # Same-size edits within one second can otherwise reuse stale Python bytecode.
    caches = []
    for name in files:
        if name.endswith('.py'):
            for cache in (target / '__pycache__').glob(Path(name).stem + '.*.pyc'):
                safe(cache)
                caches.append(cache)
    for cache in caches:
        cache.unlink()
    changed = []
    try:
        for name, value in files.items():
            changed.append(name)
            atomic(target / name, *value)
    except BaseException:
        for name in reversed(changed):
            old = previous[name]
            if old is None:
                if (target / name).exists():
                    (target / name).unlink()
            else:
                atomic(target / name, *old)
        raise


def check(app):
    if app.get('self_update'):
        return check_self(app)
    old = current(app)
    commit = revision(api(app['repo'] + '/commits/' + app['branch'])['sha'])
    item = api(app['repo'] + '/contents/' + app['source'] + '?ref=' + commit)
    if (item.get('type') != 'file' or item.get('encoding') != 'base64'
            or item.get('path') != app['source']):
        raise ValueError('Unexpected GitHub file')
    data = base64.b64decode(''.join(item['content'].split()), validate=True)
    if not data or len(data) > LIMIT or len(data) != item['size']:
        raise ValueError('Invalid download size')
    if git_sha(data) != revision(item['sha']):
        raise ValueError('Download checksum failed')
    compile(data, app['source'], 'exec')
    return dict(commit=commit, version=source_version(data) or commit[:8],
                data=data, old=sha(old) if old is not None else None,
                needed=data != old or incomplete(app))


def atomic(path, content, mode=0o600):
    fd, name = tempfile.mkstemp(prefix='.update-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, mode)
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def process_identity(proc, app):
    """Match only our user's Python script, retaining its process start time."""
    try:
        if proc.stat().st_uid != os.getuid() or int(proc.name) == os.getpid():
            return None
        args = (proc / 'cmdline').read_bytes().split(b'\0')
        if (len(args) < 2 or not Path(os.fsdecode(args[0])).name.startswith('python')
                or args[1] != os.fsencode(app['path'])):
            return None
        # comm may contain spaces or parentheses; fields after it start at field 3.
        return (proc / 'stat').read_text().rsplit(')', 1)[1].split()[19]
    except FileNotFoundError:
        return None


def running_processes(app):
    found = {}
    for proc in Path('/proc').glob('[0-9]*'):
        identity = process_identity(proc, app)
        if identity is not None:
            found[int(proc.name)] = identity
    return found


def running(app):
    return bool(running_processes(app))


def close_app(app, processes, timeout=8):
    for pid, identity in processes.items():
        if process_identity(Path('/proc') / str(pid), app) != identity:
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + timeout
    while running(app):
        if time.monotonic() >= deadline:
            raise ValueError(app['name'] + ' did not close. Update skipped; try again.')
        time.sleep(0.1)


def install(app, result):
    if not result['needed']:
        return
    if app.get('self_update'):
        install_self(app, result)
        return
    if running(app):
        raise ValueError('Close ' + app['name'] + ' first, then try again.')
    old = current(app)
    if (sha(old) if old is not None else None) != result['old']:
        raise ValueError('App changed. Check for updates again.')
    compile(result['data'], app['source'], 'exec')
    if old is None or incomplete(app):
        from deployment import deploy
        source = Path(__file__).resolve().parent
        files = {app['source']: (result['data'], 0o644),
                 'launch': ((source / 'bitcoin-launch').read_bytes(), 0o755),
                 'bitcoin.png': ((source / 'bitcoin.png').read_bytes(), 0o644)}
        if old is not None:
            # Repair missing support files without replacing working custom ones.
            from deployment import safe
            for name in ('launch', 'bitcoin.png'):
                path = app['path'].parent / name
                safe(path)
                if path.is_file() and (name != 'launch' or os.access(path, os.X_OK)):
                    files[name] = (path.read_bytes(), path.stat().st_mode & 0o777)
        deploy(HOME, app['path'].parent, app['name'], 'bitcoin.png', files)
        return
    # One executable file is the complete app; replace it in one atomic rename.
    # Receipts are keyed by content, so an interrupted install cannot mislabel it.
    receipts = DATA / 'receipts'
    receipts.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt = json.dumps(dict(repo=app['repo'], commit=revision(result['commit']))).encode()
    atomic(receipts / (sha(result['data']) + '.json'), receipt)
    atomic(app['path'].with_suffix('.py.before-update'), old)
    atomic(app['path'], result['data'], 0o644)


def bind_navigation(widget, move, activate):
    """Handle keypad keys before Tk's widget class bindings consume them."""
    for keys, step, vertical in (
            (('Up', 'KP_Up'), -1, True), (('Down', 'KP_Down'), 1, True),
            (('Left', 'KP_Left', 'Shift-Tab', 'ISO_Left_Tab'), -1, False),
            (('Right', 'KP_Right', 'Tab'), 1, False)):
        for key in keys:
            widget.bind('<' + key + '>',
                        lambda event, step=step, vertical=vertical: move(step, vertical))
    for key in ('Return', 'KP_Enter', 'space'):
        widget.bind('<' + key + '>', activate)


class Window:
    def __init__(self, root):
        self.root = root
        self.results = {}
        self.selected = set()
        self.busy = False
        self.restart_required = False
        self.show_requested = False
        self.events = queue.Queue()
        root.title('Update Apps')
        root.geometry('480x272+0+0')
        root.attributes('-fullscreen', True)
        root.configure(bg='#101923')
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.bind('<Escape>', lambda e: self.close())
        root.bind('<Home>', lambda e: self.close())
        root.bind('<Key-c>', lambda e: self.start('check'))
        root.bind('<Key-i>', lambda e: self.start('install'))
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('Treeview', background='#1b2938', fieldbackground='#1b2938',
                        foreground='#f1f5fa', rowheight=38, font=('DejaVu Sans', 10))
        style.map('Treeview', background=[('selected', '#31556f')],
                  foreground=[('selected', '#ffffff')])
        style.configure('Treeview.Heading', font=('DejaVu Sans', 9, 'bold'))
        top = tk.Frame(root, bg='#101923')
        top.pack(fill='x', padx=10, pady=(7, 4))
        tk.Label(top, text='Update Apps', bg='#101923', fg='#f1f5fa',
                 font=('DejaVu Sans', 17, 'bold')).pack(side='left')
        self.home = tk.Button(top, text='Home', command=self.close)
        self.home.pack(side='right')
        body = tk.Frame(root)
        body.pack(fill='both', expand=True, padx=10)
        self.list = ttk.Treeview(body, columns=('app', 'installed', 'latest'),
                                 show='tree headings', selectmode='none', height=2)
        self.list.column('#0', width=44, minwidth=44, stretch=False)
        self.list.heading('#0', text='')
        self.checkbox_images = [self.checkbox_image(False), self.checkbox_image(True)]
        self.list.bind('<ButtonRelease-1>', self.toggle_row)
        self.list.bind('<FocusIn>', lambda e: self.focus_row())
        for key, label, width in [('app', 'App', 164), ('installed', 'Installed', 112),
                                  ('latest', 'Latest', 112)]:
            self.list.heading(key, text=label)
            self.list.column(key, width=width, minwidth=width, stretch=True)
        scroll = ttk.Scrollbar(body, orient='vertical', command=self.list.yview)
        self.list.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.list.pack(side='left', fill='both', expand=True)
        for index, app in enumerate(APPS):
            try:
                version = installed(app)
            except (OSError, ValueError, SyntaxError):
                version = 'not installed'
            self.list.insert('', 'end', iid=str(index), image=self.checkbox_images[0], values=(app['name'], version, 'Unchecked'))
        self.status = tk.Label(root, text='Check for updates, then tick the apps to install.',
                               bg='#101923', fg='#b8c8d9', wraplength=456,
                               font=('DejaVu Sans', 9), anchor='w', justify='left', height=2)
        self.status.pack(fill='x', padx=10, pady=3)
        buttons = tk.Frame(root, bg='#101923')
        buttons.pack(fill='x', padx=10, pady=(0, 8))
        self.check_button = tk.Button(buttons, text='Check for updates', height=2,
                                       command=lambda: self.start('check'))
        self.check_button.pack(side='left', fill='x', expand=True, padx=(0, 5))
        self.install_button = tk.Button(buttons, text='Install selected', height=2,
                                         state='disabled', command=lambda: self.start('install'))
        self.install_button.pack(side='left', fill='x', expand=True, padx=(5, 0))
        for button in (self.home, self.check_button, self.install_button):
            button.configure(takefocus=True, highlightthickness=2,
                             highlightbackground='#101923', highlightcolor='#60d6ac')
        for widget in (root, self.list, self.home, self.check_button, self.install_button):
            bind_navigation(widget, self.move_focus, self.activate_focused)
        root.after_idle(self.focus_navigation)
        root.after(100, self.poll)

    def checkbox_image(self, checked):
        image = tk.PhotoImage(master=self.root, width=20, height=20)
        image.put('#b8c8d9', to=(1, 1, 19, 19))
        image.put('#1b2938', to=(3, 3, 17, 17))
        if checked:
            for x, y in ((5, 10), (6, 11), (7, 12), (8, 13), (9, 12),
                         (10, 11), (11, 10), (12, 9), (13, 8), (14, 7)):
                image.put('#60d6ac', to=(x, y, x + 2, y + 2))
        return image

    def pending_selection(self):
        return frozenset(index for index in self.selected
                         if self.results.get(index, {}).get('needed', False))

    def update_install_button(self):
        enabled = not self.busy and not self.restart_required and self.pending_selection()
        self.install_button.configure(state='normal' if enabled else 'disabled')

    def toggle_row(self, event):
        row = self.list.identify_row(event.y)
        if self.list.identify_region(event.x, event.y) in ('tree', 'cell') and row:
            self.focus_row(row)
            self.list.focus_set()
            self.toggle_index(int(row))
        return 'break'

    def toggle_focused(self, event):
        row = self.list.focus()
        if row:
            self.toggle_index(int(row))
        return 'break'

    def focus_row(self, row=None):
        rows = self.list.get_children()
        if rows:
            row = row or self.list.focus() or rows[0]
            self.list.focus(row)
            # Treeview selection marks keyboard focus; only checkboxes choose installs.
            self.list.selection_set(row)
            self.list.see(row)

    def navigation_widgets(self):
        if self.restart_required:
            return (self.home,)
        return tuple(widget for widget in (self.home, self.list, self.check_button,
                                           self.install_button)
                     if widget is self.list or str(widget['state']) != 'disabled')

    def focus_navigation(self, force=False):
        dialog = self.root.grab_current()
        if dialog is not None:
            if force:
                dialog.lift()
                dialog.focus_lastfor().focus_force()
            return
        focused = self.root.focus_get()
        if focused not in self.navigation_widgets():
            focused = self.home if self.restart_required else self.list
        if force:
            focused.focus_force()
        else:
            focused.focus_set()

    def move_focus(self, step, vertical=True):
        if self.busy:
            return 'break'
        focused = self.root.focus_get()
        if focused is self.list and vertical and not self.restart_required:
            rows = self.list.get_children()
            row = self.list.focus()
            index = rows.index(row) if row in rows else (-1 if step > 0 else len(rows))
            if 0 <= index + step < len(rows):
                self.focus_row(rows[index + step])
                return 'break'
        widgets = self.navigation_widgets()
        index = widgets.index(focused) if focused in widgets else (-1 if step > 0 else len(widgets))
        target = widgets[(index + step) % len(widgets)]
        if target is self.list and vertical:
            rows = self.list.get_children()
            if rows:
                self.focus_row(rows[0 if step > 0 else -1])
        target.focus_set()
        return 'break'

    def activate_focused(self, event):
        if not self.busy:
            focused = self.root.focus_get()
            if focused is self.list and not self.restart_required:
                self.toggle_focused(event)
            elif focused in (self.home, self.check_button, self.install_button):
                focused.invoke()
        return 'break'

    def toggle_index(self, index):
        if self.busy or self.restart_required:
            return
        if index in self.selected:
            self.selected.remove(index)
        else:
            self.selected.add(index)
        self.list.item(str(index), image=self.checkbox_images[int(index in self.selected)])
        self.update_install_button()

    def close(self):
        if not self.busy:
            self.root.destroy()

    def start(self, action):
        if self.restart_required or self.busy or (action == 'install' and not self.pending_selection()):
            return
        self.busy = True
        for button in (self.check_button, self.install_button, self.home):
            button.configure(state='disabled')
        self.status.configure(text='Checking GitHub...' if action == 'check' else 'Installing updates...')
        if action == 'check':
            self.results = {}
        threading.Thread(target=self.work, args=(action, self.pending_selection()), daemon=True).start()

    def confirm_close(self, app):
        answer = []
        ready = threading.Event()
        self.events.put(('confirm-close', app['name'], answer, ready))
        ready.wait()
        return bool(answer and answer[0])

    def show_close_prompt(self, name, answer, ready):
        # Small touch targets and system dialogs do not fit PocketCHIP reliably.
        dialog = tk.Toplevel(self.root)
        dialog.title('Close app to update')
        dialog.geometry('440x190+20+40')
        dialog.transient(self.root)
        dialog.resizable(False, False)
        tk.Label(dialog, text='Close ' + name + ' and install its update?\n'
                 'Unsaved work may be lost. It will stay closed.',
                 wraplength=410, font=('DejaVu Sans', 11), justify='left').pack(
                     fill='x', padx=14, pady=18)
        def finish(approved):
            answer.append(approved)
            dialog.grab_release()
            dialog.destroy()
            ready.set()
        buttons = tk.Frame(dialog)
        buttons.pack(fill='x', padx=14)
        cancel = tk.Button(buttons, text='Cancel', height=2, command=lambda: finish(False))
        cancel.pack(side='left', expand=True, fill='x', padx=(0, 6))
        approve = tk.Button(buttons, text='Close and update', height=2,
                            command=lambda: finish(True))
        approve.pack(side='left', expand=True, fill='x')
        choices = (cancel, approve)
        def move(step, vertical):
            focused = dialog.focus_get()
            index = choices.index(focused) if focused in choices else 0
            choices[(index + step) % len(choices)].focus_set()
            return 'break'
        def activate(event):
            focused = dialog.focus_get()
            # An unfocused prompt always defaults to Cancel.
            (focused if focused in choices else cancel).invoke()
            return 'break'
        for button in choices:
            button.configure(takefocus=True, highlightthickness=2, highlightcolor='#23805f')
        for widget in (dialog, cancel, approve):
            bind_navigation(widget, move, activate)
        dialog.protocol('WM_DELETE_WINDOW', lambda: finish(False))
        dialog.bind('<Escape>', lambda e: finish(False))
        dialog.bind('<Home>', lambda e: finish(False))
        dialog.wait_visibility()
        dialog.grab_set()
        cancel.focus_set()

    def work(self, action, selected=frozenset()):
        errors = []
        count = 0
        for index, app in enumerate(APPS):
            try:
                if action == 'check':
                    result = check(app)
                    self.results[index] = result
                    version = installed(app) if result['needed'] else result['version']
                    self.events.put(('row', index, version, result['version']))
                    count += int(result['needed'])
                elif index in selected and index in self.results and self.results[index]['needed']:
                    if not app.get('self_update'):
                        processes = running_processes(app)
                        if processes:
                            if not self.confirm_close(app):
                                errors.append(app['name'] + ': update cancelled.')
                                continue
                            close_app(app, processes)
                    install(app, self.results[index])
                    if app.get('self_update'):
                        self.restart_required = True
                    self.results[index]['needed'] = False
                    self.events.put(('row', index, installed(app), self.results[index]['version']))
                    count += 1
            except Exception as error:
                errors.append(app['name'] + ': ' + str(error))
        if errors:
            message = '; '.join(errors)
        elif action == 'check':
            message = ('%d app(s) available. Tick apps, then Install selected.' % count
                       if count else 'All apps are up to date.')
        else:
            message = '%d app(s) installed. Restart Home for new icons.' % count
        if self.restart_required:
            message = 'App Updater updated. Tap Home to finish; launch it when needed.' + (' ' + message if errors else '')
        self.events.put(('done', message))

    def request_show(self, *_):
        # Signal handlers can interrupt Queue operations while its lock is held.
        # Only set a flag here; Tk and Queue calls belong in the normal event loop.
        self.show_requested = True

    def poll(self):
        if self.show_requested:
            self.show_requested = False
            self.root.deiconify()
            self.root.lift()
            self.focus_navigation(force=True)
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == 'show':
                    self.root.deiconify()
                    self.root.lift()
                    self.focus_navigation(force=True)
                elif event[0] == 'confirm-close':
                    try:
                        self.show_close_prompt(*event[1:])
                    except Exception:
                        event[3].set()
                        raise
                elif event[0] == 'row':
                    _, index, version, latest = event
                    self.list.item(str(index), values=(APPS[index]['name'], version, latest))
                else:
                    self.busy = False
                    self.status.configure(text=event[1])
                    self.check_button.configure(state='disabled' if self.restart_required else 'normal')
                    self.home.configure(state='normal')
                    self.update_install_button()
                    self.focus_navigation()
        except queue.Empty:
            pass
        self.root.after(100, self.poll)


def main():
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (DATA / 'updater.lock').open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.seek(0)
            try:
                pid = int(lock.read(32))
                args = (Path('/proc') / str(pid) / 'cmdline').read_bytes().split(b'\0')
                if os.fsencode(Path(__file__).resolve()) in args:
                    os.kill(pid, signal.SIGUSR1)
                    # Launchers track this process; stay alive while the existing
                    # window is open instead of making them return to Home.
                    fcntl.flock(lock, fcntl.LOCK_EX)
            except (OSError, ValueError):
                pass
            return
        root = tk.Tk()
        window = Window(root)
        signal.signal(signal.SIGUSR1, window.request_show)
        lock.seek(0)
        lock.truncate()
        lock.write(str(os.getpid()))
        lock.flush()
        root.mainloop()


if __name__ == '__main__':
    main()
