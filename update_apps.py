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
import tkinter as tk
from tkinter import ttk
from urllib.request import Request, urlopen

VERSION = '1.1.0'
HOME = Path.home()
DATA = HOME / '.local/share/pocket-update-apps'
# Explicit trusted catalog. Only these single-file Python apps are updated.
APPS = [dict(name='Bitcoin CAD', repo='csd113/PocketChip-Bitcoin-Display',
             branch='main', source='bitcoin.py',
             path=HOME / '.local/share/pocket-bitcoin/bitcoin.py',
             known={'14d91cc19782ced7716132a0563161bdb8cd9b86c3ceffb8053ee9409b158ccd':
                    'cd1f1d7a2a5fed4c4441abcb78c1c924fb4b6f16'})]
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


def installed(app):
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


def check(app):
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
                data=data, old=sha(old) if old is not None else None, needed=data != old)


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


def running(app):
    for proc in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            args = proc.read_bytes().split(b'\0')
            if os.fsencode(app['path']) in args:
                return True
        except OSError:
            continue
    return False


def install(app, result):
    if not result['needed']:
        return
    if running(app):
        raise ValueError('Close ' + app['name'] + ' first, then try again.')
    old = current(app)
    if (sha(old) if old is not None else None) != result['old']:
        raise ValueError('App changed. Check for updates again.')
    compile(result['data'], app['source'], 'exec')
    if old is None:
        from deployment import deploy
        source = Path(__file__).resolve().parent
        files = {app['source']: (result['data'], 0o644),
                 'launch': ((source / 'bitcoin-launch').read_bytes(), 0o755),
                 'bitcoin.png': ((source / 'bitcoin.png').read_bytes(), 0o644)}
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


class Window:
    def __init__(self, root):
        self.root = root
        self.results = {}
        self.busy = False
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
                                 show='headings', selectmode='none', height=2)
        for key, label, width in [('app', 'App', 176), ('installed', 'Installed', 126),
                                  ('latest', 'Latest', 126)]:
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
            self.list.insert('', 'end', iid=str(index), values=(app['name'], version, 'Unchecked'))
        self.status = tk.Label(root, text='Tap Check to find the latest app versions.',
                               bg='#101923', fg='#b8c8d9', wraplength=456,
                               font=('DejaVu Sans', 9), anchor='w', justify='left', height=2)
        self.status.pack(fill='x', padx=10, pady=3)
        buttons = tk.Frame(root, bg='#101923')
        buttons.pack(fill='x', padx=10, pady=(0, 8))
        self.check_button = tk.Button(buttons, text='Check for updates', height=2,
                                       command=lambda: self.start('check'))
        self.check_button.pack(side='left', fill='x', expand=True, padx=(0, 5))
        self.install_button = tk.Button(buttons, text='Install / update', height=2,
                                         state='disabled', command=lambda: self.start('install'))
        self.install_button.pack(side='left', fill='x', expand=True, padx=(5, 0))
        root.after(100, self.poll)

    def close(self):
        if not self.busy:
            self.root.destroy()

    def start(self, action):
        if self.busy or (action == 'install' and not any(r['needed'] for r in self.results.values())):
            return
        self.busy = True
        for button in (self.check_button, self.install_button, self.home):
            button.configure(state='disabled')
        self.status.configure(text='Checking GitHub...' if action == 'check' else 'Installing updates...')
        if action == 'check':
            self.results = {}
        threading.Thread(target=self.work, args=(action,), daemon=True).start()

    def work(self, action):
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
                elif index in self.results and self.results[index]['needed']:
                    install(app, self.results[index])
                    self.results[index]['needed'] = False
                    self.events.put(('row', index, installed(app), self.results[index]['version']))
                    count += 1
            except Exception as error:
                errors.append(app['name'] + ': ' + str(error))
        if errors:
            message = '; '.join(errors)
        elif action == 'check':
            message = ('%d app(s) to install/update. Close open apps first.' % count
                       if count else 'All apps are up to date.')
        else:
            message = '%d app(s) installed. Restart Home for new icons.' % count
        self.events.put(('done', message))

    def poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == 'show':
                    self.root.deiconify()
                    self.root.lift()
                    self.root.focus_force()
                elif event[0] == 'row':
                    _, index, version, latest = event
                    self.list.item(str(index), values=(APPS[index]['name'], version, latest))
                else:
                    self.busy = False
                    self.status.configure(text=event[1])
                    self.check_button.configure(state='normal')
                    self.home.configure(state='normal')
                    self.install_button.configure(state='normal' if any(
                        r['needed'] for r in self.results.values()) else 'disabled')
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
            except (OSError, ValueError):
                pass
            return
        root = tk.Tk()
        window = Window(root)
        signal.signal(signal.SIGUSR1, lambda *_: window.events.put(('show',)))
        lock.seek(0)
        lock.truncate()
        lock.write(str(os.getpid()))
        lock.flush()
        root.mainloop()


if __name__ == '__main__':
    main()
