"""Validated file and PocketHome shortcut installation with rollback."""
import json
from pathlib import Path
import shlex
import time


def safe(path):
    path = Path(path)
    if any(p.is_symlink() for p in (path,) + tuple(path.parents)):
        raise ValueError('Refusing symlink path: ' + str(path))
    if path.exists() and not path.is_file():
        raise ValueError('Expected a regular file: ' + str(path))


def deploy(home, target, name, icon, files, validate_only=False):
    from update_apps import atomic
    config_path = home / '.pocket-home/config.json'
    safe(config_path)
    original = config_path.read_bytes()
    config = json.loads(original)
    pages = [p for p in config['pages'] if p.get('name') == 'Apps']
    if len(pages) != 1 or not isinstance(pages[0].get('items'), list):
        raise ValueError('Expected exactly one PocketHome Apps page')
    items = pages[0]['items']
    if not all(isinstance(item, dict) for item in items):
        raise ValueError('Invalid PocketHome menu item')
    matches = [i for i in items if i.get('name') == name]
    if len(matches) > 1:
        raise ValueError('Duplicate Home menu entries: ' + name)
    entry = dict(name=name, icon=str(target / icon), shell=shlex.quote(str(target / 'launch')))
    if matches:
        matches[0].update(entry)
    else:
        items.append(entry)
    writes = {}
    for filename, value in files.items():
        if Path(filename).name != filename:
            raise ValueError('Invalid installer filename')
        if filename.endswith('.py'):
            compile(value[0], filename, 'exec')
        writes[target / filename] = value
    desktop = ('[Desktop Entry]\nType=Application\nName=' + name + '\nExec="' +
               str(target / 'launch').replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$') +
               '"\nIcon=' + str(target / icon) + '\nTerminal=false\nCategories=Utility;\n')
    if any(c in str(target) for c in '\n\r%'):
        raise ValueError('Unsupported installation path')
    for directory in (home / '.local/share/applications', home / 'Desktop'):
        writes[directory / (target.name + '.desktop')] = (desktop.encode(), 0o755)
    writes[config_path] = ((json.dumps(config, indent=2) + '\n').encode(), 0o644)
    previous = {}
    for path in writes:
        safe(path)
        previous[path] = (path.read_bytes(), path.stat().st_mode & 0o777) if path.exists() else None
    if validate_only:
        return
    backup = config_path.with_name('config.json.before-app-install-' + str(time.time_ns()))
    atomic(backup, original)
    changed = []
    try:
        for path, (content, mode) in writes.items():
            safe(path)
            if path == config_path and path.read_bytes() != original:
                raise ValueError('Menu changed during installation; retry')
            path.parent.mkdir(parents=True, exist_ok=True)
            changed.append(path)
            atomic(path, content, mode)
    except BaseException:
        for path in reversed(changed):
            old = previous[path]
            if old is None:
                if path.exists():
                    path.unlink()
            else:
                atomic(path, *old)
        raise
