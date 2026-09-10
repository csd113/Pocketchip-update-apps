#!/usr/bin/env python3
"""Run on PocketCHIP, using its Python/Tk runtime, to add Update Apps."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
from update_apps import atomic

source = Path(__file__).resolve().parent
home = Path.home()
target = home / '.local/share/pocket-update-apps'
config_path = home / '.pocket-home/config.json'
original = config_path.read_bytes()
config = json.loads(original)
pages = [page for page in config['pages'] if page.get('name') == 'Apps']
if len(pages) != 1 or not isinstance(pages[0].get('items'), list):
    raise SystemExit('Expected one Apps page; menu was not changed')
if target.exists() or target.is_symlink():
    raise SystemExit('Updater directory already exists; refusing to overwrite')
if any(item.get('name') == 'Update Apps' for item in pages[0]['items']):
    raise SystemExit('Update Apps menu item already exists')
files = ['update_apps.py', 'launch', 'update-apps.png', 'test_update_apps.py', 'check_layout.py', 'README.md']
for name in files:
    if not (source / name).is_file() or (source / name).is_symlink():
        raise SystemExit('Missing or unsafe source: ' + name)
    if name.endswith('.py'):
        compile((source / name).read_bytes(), name, 'exec')
pages[0]['items'].insert(1, dict(name='Update Apps', icon=str(target / 'update-apps.png'),
                               shell=str(target / 'launch')))
updated = (json.dumps(config, indent=2) + '\n').encode()
backup = config_path.with_name('config.json.before-update-apps-' + time.strftime('%Y%m%d-%H%M%S'))
atomic(backup, original)
staged = Path(tempfile.mkdtemp(prefix='.updater-install-', dir=target.parent))
try:
    for name in files:
        shutil.copyfile(source / name, staged / name)
        (staged / name).chmod(0o755 if name == 'launch' else 0o644)
    if config_path.read_bytes() != original:
        raise RuntimeError('Menu changed during installation; retry after review')
    os.rename(staged, target)
    try:
        atomic(config_path, updated, 0o644)
    except BaseException:
        atomic(config_path, original, 0o644)
        shutil.rmtree(target)
        raise
finally:
    if staged.exists():
        shutil.rmtree(staged)
print('Installed:', target)
print('Menu backup:', backup)
