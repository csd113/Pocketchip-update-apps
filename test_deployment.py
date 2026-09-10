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
