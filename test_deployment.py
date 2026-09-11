import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import update_apps as u
from deployment import deploy


class Deployment(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.config = self.home / '.pocket-home/config.json'
        self.config.parent.mkdir()
        self.config.write_text(json.dumps({'pages': [{'name': 'Apps', 'items': [{'name': 'Terminal'}]}]}))
        self.target = self.home / '.local/share/pocket-bitcoin'
        self.app = dict(u.APPS[0], path=self.target / 'bitcoin.py')
        self.result = dict(needed=True, old=None, data=b"VERSION = '1.0.0'\n", commit='a'*40)
        self.result.update(catalog_id=self.app['id'], version='v1.0.0',
                           sha256=u.sha(self.result['data']))

    def install(self):
        with patch.object(u, 'HOME', self.home), patch.object(u, 'running', return_value=False):
            u.install(self.app, self.result)

    def test_missing_app_installs_with_shortcuts(self):
        self.assertEqual(u.installed(self.app), 'not installed')
        self.install()
        self.assertTrue((self.target / 'launch').stat().st_mode & 0o111)
        self.assertTrue((self.home / 'Desktop/pocket-bitcoin.desktop').is_file())
        self.assertEqual(json.loads(self.config.read_text())['pages'][0]['items'][-1]['name'], 'Bitcoin CAD')
        self.assertEqual(u.installed(self.app), 'v1.0.0')

    def test_appeared_since_check(self):
        self.target.mkdir(parents=True)
        self.app['path'].write_text('# user app')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.install()
        self.assertEqual(self.app['path'].read_text(), '# user app')

    def test_menu_failure_rolls_back(self):
        original = self.config.read_bytes()
        real = u.atomic
        failed = []
        def write(path, data, mode=0o600):
            if path == self.config and not failed:
                failed.append(True)
                raise OSError('disk failure')
            return real(path, data, mode)
        with patch.object(u, 'atomic', side_effect=write):
            with self.assertRaises(OSError):
                self.install()
        self.assertFalse(self.app['path'].exists())
        self.assertFalse((self.home / 'Desktop/pocket-bitcoin.desktop').exists())
        self.assertEqual(self.config.read_bytes(), original)

    def test_repeat_deployment_does_not_duplicate_menu(self):
        for _ in range(2):
            deploy(self.home, self.target, 'Bitcoin CAD', 'bitcoin.png', {'launch': (b'#!/bin/sh\n', 0o755)})
        self.assertEqual(len(json.loads(self.config.read_text())['pages'][0]['items']), 2)

    def test_symlink_parent_rejected(self):
        outside = self.home / 'outside'
        outside.mkdir()
        (self.home / '.local').symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.install()
        self.assertEqual(list(outside.iterdir()), [])

    def test_invalid_menu_preserves_files(self):
        self.config.write_text('{"pages": []}')
        with self.assertRaises(ValueError):
            self.install()
        self.assertFalse(self.target.exists())

    def test_interruption_is_visible_and_reinstall_repairs(self):
        import os
        import subprocess
        import sys
        script = """
from pathlib import Path
import os
import update_apps as u
from deployment import deploy
home = Path(os.environ['TEST_HOME'])
real = u.atomic
def interrupted(path, data, mode=0o600):
    real(path, data, mode)
    if path.name == 'bitcoin.py':
        os._exit(91)
u.atomic = interrupted
deploy(home, home / '.local/share/pocket-bitcoin', 'Bitcoin CAD', 'bitcoin.png',
       {'bitcoin.py': (b"VERSION = '1.0.0'\\n", 0o644)})
"""
        env = dict(os.environ, TEST_HOME=str(self.home),
                   PYTHONPATH=str(Path(u.__file__).parent) + os.pathsep + os.environ.get('PYTHONPATH', ''))
        result = subprocess.run([sys.executable, '-c', script], env=env, check=False)
        self.assertEqual(result.returncode, 91)
        self.assertEqual(u.installed(self.app), 'incomplete / repair')
        self.result['old'] = u.sha(self.app['path'].read_bytes())
        self.install()
        self.assertFalse((self.target / '.installation-pending').exists())
        self.assertEqual(u.installed(self.app), 'v1.0.0')
        self.assertTrue((self.target / 'launch').is_file())

    def test_missing_launcher_is_repaired(self):
        self.install()
        (self.target / 'launch').unlink()
        self.assertEqual(u.installed(self.app), 'incomplete / repair')
        self.result['old'] = u.sha(self.app['path'].read_bytes())
        self.install()
        self.assertTrue((self.target / 'launch').is_file())
        self.assertEqual(u.installed(self.app), 'v1.0.0')

    def test_private_menu_permissions_are_preserved(self):
        self.config.chmod(0o600)
        self.install()
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)

    def test_malformed_documents_fail_before_mutation(self):
        for value in ([], None, {'pages': [None]}):
            self.config.write_text(json.dumps(value))
            with self.assertRaises(ValueError):
                self.install()
            self.assertFalse(self.target.exists())

    def test_hardlinked_menu_is_preserved(self):
        import os
        outside = self.home / 'outside'
        os.link(self.config, outside)
        original = outside.read_bytes()
        with self.assertRaisesRegex(ValueError, 'hardlink'):
            self.install()
        self.assertEqual(outside.read_bytes(), original)

    def test_dangling_marker_requires_repair(self):
        self.target.mkdir(parents=True)
        (self.target / '.installation-pending').symlink_to(self.target / 'missing')
        self.assertEqual(u.installed(self.app), 'incomplete / repair')

    def test_invalid_bundle_paths_and_labels_are_rejected(self):
        for filename in ('../outside', '..', '', '/outside', '.installation-pending',
                         'file\nExec=bad', None):
            with self.assertRaises(ValueError):
                deploy(self.home, self.target, 'App', 'icon.png', {filename: (b'x', 0o644)})
        for name in ('App\nExec=bad', None, 123):
            with self.assertRaises(ValueError):
                deploy(self.home, self.target, name, 'icon.png', {})
        for icon in ('../outside', '..', '', '/outside', 'icon\nExec=bad', None):
            with self.assertRaises(ValueError):
                deploy(self.home, self.target, 'App', icon, {})
        self.assertFalse(self.target.exists())
        self.assertEqual(list(self.config.parent.glob('*.before-app-install-*')), [])

    def test_failure_after_atomic_rename_rolls_back(self):
        real = u.atomic
        failed = []
        def write(path, *args):
            real(path, *args)
            if path == self.app['path'] and not failed:
                failed.append(True)
                raise OSError('directory fsync failure')
        with patch.object(u, 'atomic', side_effect=write):
            with self.assertRaises(OSError):
                self.install()
        self.assertFalse(self.app['path'].exists())
        self.assertTrue((self.target / '.installation-pending').exists())

    def test_oversized_config_fails_before_mutation(self):
        original = self.config.read_bytes()
        self.config.write_bytes(original + b' ' * (1024 * 1024 + 1 - len(original)))
        with self.assertRaisesRegex(ValueError, '1 MiB'):
            self.install()
        self.assertFalse(self.target.exists())
        self.assertEqual(list(self.config.parent.glob('*.before-app-install-*')), [])

    def test_unsafe_marker_is_rejected_before_backup_or_install(self):
        self.target.mkdir(parents=True)
        outside = self.home / 'outside'
        outside.write_bytes(b'keep')
        (self.target / '.installation-pending').symlink_to(outside)
        for validate_only in (True, False):
            with self.subTest(validate_only=validate_only):
                with self.assertRaisesRegex(ValueError, 'symlink'):
                    deploy(self.home, self.target, 'Bitcoin CAD', 'bitcoin.png',
                           {'bitcoin.py': (b'print(1)\n', 0o644)}, validate_only=validate_only)
                self.assertEqual(outside.read_bytes(), b'keep')
                self.assertFalse(self.app['path'].exists())
                self.assertEqual(list(self.config.parent.glob('*.before-app-install-*')), [])

    def test_file_edit_after_validation_is_preserved(self):
        self.install()
        real = u.atomic
        def write(path, *args):
            real(path, *args)
            if path.name == '.installation-pending':
                self.app['path'].write_bytes(b'# user edit\n')
        with patch.object(u, 'atomic', side_effect=write):
            with self.assertRaisesRegex(ValueError, 'changed during installation'):
                deploy(self.home, self.target, 'Bitcoin CAD', 'bitcoin.png',
                       {'bitcoin.py': (b'print(2)\n', 0o644)})
        self.assertEqual(self.app['path'].read_bytes(), b'# user edit\n')
        self.assertTrue((self.target / '.installation-pending').exists())

    def test_menu_permission_change_after_validation_is_preserved(self):
        real = u.atomic
        def write(path, *args):
            real(path, *args)
            if path.name == '.installation-pending':
                self.config.chmod(0o600)
        with patch.object(u, 'atomic', side_effect=write):
            with self.assertRaisesRegex(ValueError, 'changed during installation'):
                self.install()
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        self.assertFalse(self.app['path'].exists())

    def test_menu_edit_during_preparation_is_preserved(self):
        from deployment import safe
        changed = []
        edited = b'{"pages": [{"name": "Apps", "items": [{"name": "User app"}]}]}'
        def validate(path):
            safe(path)
            if path == self.app['path'] and not changed:
                changed.append(True)
                self.config.write_bytes(edited)
                self.config.chmod(0o600)
        with patch('deployment.safe', side_effect=validate):
            with self.assertRaisesRegex(ValueError, 'changed during installation'):
                self.install()
        self.assertEqual(self.config.read_bytes(), edited)
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        self.assertFalse(self.app['path'].exists())

    def test_rollback_preserves_later_file_edits(self):
        real = u.atomic
        original = self.config.read_bytes()
        def write(path, *args):
            if path == self.config:
                self.app['path'].write_bytes(b'# later user edit\n')
                raise OSError('menu write failed')
            real(path, *args)
        with patch.object(u, 'atomic', side_effect=write):
            with self.assertRaisesRegex(OSError, 'menu write failed'):
                self.install()
        self.assertEqual(self.app['path'].read_bytes(), b'# later user edit\n')
        self.assertEqual(self.config.read_bytes(), original)
        self.assertTrue((self.target / '.installation-pending').exists())

    def test_icon_repair_preserves_working_custom_launcher(self):
        self.install()
        launcher = self.target / 'launch'
        launcher.write_bytes(b'#!/bin/sh\n# custom launcher\n')
        launcher.chmod(0o700)
        (self.target / 'bitcoin.png').unlink()
        self.result['old'] = u.sha(self.app['path'].read_bytes())
        self.install()
        self.assertEqual(launcher.read_bytes(), b'#!/bin/sh\n# custom launcher\n')
        self.assertEqual(launcher.stat().st_mode & 0o777, 0o700)
        self.assertTrue((self.target / 'bitcoin.png').is_file())
        self.assertEqual(u.installed(self.app), 'v1.0.0')

    def test_nonexecutable_launcher_is_repaired(self):
        self.install()
        launcher = self.target / 'launch'
        launcher.chmod(0o600)
        self.assertEqual(u.installed(self.app), 'incomplete / repair')
        self.result['old'] = u.sha(self.app['path'].read_bytes())
        self.install()
        self.assertTrue(launcher.stat().st_mode & 0o111)
        self.assertEqual(u.installed(self.app), 'v1.0.0')
