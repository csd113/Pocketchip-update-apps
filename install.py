#!/usr/bin/env python3
"""Install or upgrade Update Apps and its Home/desktop shortcuts."""
from pathlib import Path
import shutil
import os
import tempfile
from deployment import deploy, safe


def main():
    source = Path(__file__).resolve().parent
    home = Path.home()
    target = home / '.local/share/pocket-update-apps'
    safe(target / 'update_apps.py')
    safe(home / '.pocket-home/config.json')
    files = {}
    for name in ('update_apps.py', 'deployment.py', 'launch', 'update-apps.png',
                 'bitcoin-launch', 'bitcoin.png', 'test_update_apps.py',
                 'test_deployment.py', 'check_layout.py', 'README.md'):
        path = source / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('Missing or unsafe installer file: ' + name)
        files[name] = (path.read_bytes(), 0o755 if name.endswith('launch') else 0o644)
    deploy(home, target, 'Update Apps', 'update-apps.png', files, validate_only=True)
    # Retain the existing device-specific runtime independently of Bitcoin.
    runtime = home / '.local/share/pocket-bitcoin/runtime'
    own = target / 'runtime'
    if runtime.is_dir() and not own.exists():
        target.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix='.runtime-', dir=target))
        try:
            shutil.copytree(runtime, stage / 'runtime', symlinks=True)
            os.rename(stage / 'runtime', own)
        finally:
            shutil.rmtree(stage)
    deploy(home, target, 'Update Apps', 'update-apps.png', files)
    print('Update Apps installed. Restart PocketHome to reload new icons.')


if __name__ == '__main__':
    main()
