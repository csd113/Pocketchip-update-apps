import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import update_apps as u


class Updates(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'bitcoin.py'
        self.path.write_bytes(b'print("old")\n')
        self.app = dict(name='Test', repo='owner/repo', branch='main', source='bitcoin.py',
                        path=self.path, known={})
        self.data = b'print("new")\n'
        self.commit = 'a' * 40
        self.item = dict(type='file', encoding='base64', path='bitcoin.py',
                         content=base64.b64encode(self.data).decode(), size=len(self.data),
                         sha=u.git_sha(self.data))
        p = patch.object(u, 'DATA', self.root / 'updater')
        p.start()
        self.addCleanup(p.stop)

    def result(self):
        with patch.object(u, 'api', side_effect=[{'sha': self.commit}, self.item]) as api:
            result = u.check(self.app)
        self.assertIn('?ref=' + self.commit, api.call_args.args[0])
        return result

    def test_verified_install_and_backup(self):
        old = self.path.read_bytes()
        result = self.result()
        with patch.object(u, 'running', return_value=False):
            u.install(self.app, result)
        self.assertEqual(self.path.read_bytes(), self.data)
        self.assertEqual(self.path.with_suffix('.py.before-update').read_bytes(), old)
        self.assertEqual(u.installed(self.app), 'aaaaaaaa')

    def test_checksum_mismatch(self):
        self.item['sha'] = 'b' * 40
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.result()
        self.assertEqual(self.path.read_bytes(), b'print("old")\n')

    def test_invalid_python(self):
        self.data = b'def broken('

        self.item.update(content=base64.b64encode(self.data).decode(),
                         size=len(self.data), sha=u.git_sha(self.data))
        with self.assertRaises(SyntaxError):
            self.result()

    def test_changed_since_check(self):
        result = self.result()
        self.path.write_bytes(b'# user edits\n')
        with patch.object(u, 'running', return_value=False):
            with self.assertRaisesRegex(ValueError, 'changed'):
                u.install(self.app, result)
        self.assertEqual(self.path.read_bytes(), b'# user edits\n')

    def test_open_app_is_blocked(self):
        with patch.object(u, 'running', return_value=True):
            with self.assertRaisesRegex(ValueError, 'Close'):
                u.install(self.app, self.result())

    def test_replace_failure_preserves_app(self):
        result = self.result()
        real = u.os.replace
        def replace(src, dst):
            if dst == self.path:
                raise OSError('simulated disk failure')
            return real(src, dst)
        with patch.object(u, 'running', return_value=False), patch.object(u.os, 'replace', replace):
            with self.assertRaises(OSError):
                u.install(self.app, result)
        self.assertEqual(self.path.read_bytes(), b'print("old")\n')
        self.assertEqual(u.installed(self.app), 'local / unknown')
        self.assertEqual(list(self.root.glob('.update-*')), [])

    def test_up_to_date(self):
        self.path.write_bytes(self.data)
        self.assertFalse(self.result()['needed'])

    def test_symlink_rejected(self):
        self.path.unlink()
        self.path.symlink_to(self.root / 'missing')
        with self.assertRaises(ValueError):
            u.current(self.app)

    def test_invalid_commit(self):
        self.commit = '../../bad'
        with self.assertRaises(ValueError):
            self.result()

    def test_semantic_version(self):
        self.assertEqual(u.source_version(b"VERSION = '1.0.0'\n"), 'v1.0.0')
        self.path.write_bytes(b"VERSION = '1.2.3'\n")
        self.assertEqual(u.installed(self.app), 'v1.2.3')

    def test_version_is_not_executed(self):
        with self.assertRaises(ValueError):
            u.source_version(b"VERSION = __import__('os').getcwd()\n")
        with self.assertRaises(ValueError):
            u.source_version(b"VERSION = '../../invalid'\n")

    def test_network_failure_preserves_app(self):
        with patch.object(u, 'api', side_effect=OSError('offline')):
            with self.assertRaises(OSError):
                u.check(self.app)
        self.assertEqual(self.path.read_bytes(), b'print("old")\n')


if __name__ == '__main__':
    unittest.main()
