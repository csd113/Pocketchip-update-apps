import io
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import patch
import update_apps as u


class SelfUpdate(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.app = dict(u.APPS[-1], path=self.root / 'update_apps.py')
        self.files = {name: (b"VERSION = '1.2.0'\n" if name.endswith('.py') else b'new file\n')
                      for name in u.SELF_FILES}
        self.old = {}
        for name in u.SELF_FILES:
            self.old[name] = b'# old file\n'
            (self.root / name).write_bytes(self.old[name])
        self.entries = [dict(path=name, type='blob', mode='100644', size=len(data), sha=u.git_sha(data))
                        for name, data in self.files.items()]
        self.commit = 'a' * 40

    def check(self):
        def download(request, timeout):
            self.assertIn('/' + self.commit + '/', request.full_url)
            return io.BytesIO(self.files[request.full_url.rsplit('/', 1)[1]])
        with patch.object(u, 'api', side_effect=[{'sha': self.commit}, {'tree': self.entries}]), patch.object(u, 'urlopen', side_effect=download):
            return u.check(self.app)

    def test_complete_bundle_update_while_running(self):
        result = self.check()
        with patch.object(u, 'running', return_value=True):
            u.install(self.app, result)
        for name, data in self.files.items():
            self.assertEqual((self.root / name).read_bytes(), data)
        backup, = self.root.glob('before-self-update-*')
        for name, data in self.old.items():
            self.assertEqual((backup / name).read_bytes(), data)
        self.assertTrue((self.root / 'launch').stat().st_mode & 0o111)
        self.assertFalse(self.check()['needed'])

    def test_support_file_change_detected_without_version_bump(self):
        for name, data in self.files.items():
            (self.root / name).write_bytes(data)
        (self.root / 'bitcoin-launch').write_bytes(b'old launcher')
        self.assertTrue(self.check()['needed'])

    def test_checksum_failure_preserves_installation(self):
        self.entries[-1]['sha'] = 'b' * 40
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.check()
        self.assertEqual((self.root / 'update_apps.py').read_bytes(), self.old['update_apps.py'])

    def test_symlink_from_github_rejected(self):
        self.entries[0]['mode'] = '120000'
        with self.assertRaisesRegex(ValueError, 'unsafe'):
            self.check()

    def test_changed_support_file_blocks_install(self):
        result = self.check()
        (self.root / 'launch').write_bytes(b'user edit')
        with self.assertRaisesRegex(ValueError, 'changed'):
            u.install(self.app, result)
        self.assertEqual(list(self.root.glob('before-self-update-*')), [])

    def test_failure_rolls_back_all_files(self):
        result = self.check()
        real = u.atomic
        failed = []
        def write(path, data, mode=0o600):
            if path == self.root / 'bitcoin.png' and not failed:
                failed.append(True)
                raise OSError('disk failure')
            return real(path, data, mode)
        with patch.object(u, 'atomic', side_effect=write):
            with self.assertRaises(OSError):
                u.install(self.app, result)
        for name, data in self.old.items():
            self.assertEqual((self.root / name).read_bytes(), data)

    def test_incomplete_bundle_blocked(self):
        result = self.check()
        del result['files']['launch']
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            u.install(self.app, result)

    def test_worker_requests_reopen_after_self_update(self):
        window = object.__new__(u.Window)
        window.events = queue.Queue()
        window.restart_required = False
        window.results = {0: self.check()}
        with patch.object(u, 'APPS', [self.app]):
            window.work('install', frozenset({0}))
        self.assertTrue(window.restart_required)
        self.assertIn('Tap Home to finish', list(window.events.queue)[-1][1])

    def test_running_python_can_replace_own_source(self):
        import subprocess
        import sys
        source = Path(u.__file__).read_bytes()
        (self.root / 'update_apps.py').write_bytes(source)
        (self.root / 'deployment.py').write_bytes(Path(u.__file__).with_name('deployment.py').read_bytes())
        script = '''
from pathlib import Path
import update_apps as u
app = dict(u.APPS[-1], path=Path(u.__file__))
files = {}
previous = {}
for name in u.SELF_FILES:
    data = (app['path'].parent / name).read_bytes()
    previous[name] = u.sha(data)
    if name == 'update_apps.py':
        data = data.replace(b"VERSION = '1.5.3'", b"VERSION = '1.5.4'")
    files[name] = (data, 0o644)
u.install_self(app, dict(files=files, previous=previous))
assert u.VERSION == '1.5.3'
assert u.installed(app) == 'v1.5.4'
'''
        subprocess.run([sys.executable, '-c', script], cwd=self.root, check=True, capture_output=True)
        result = subprocess.run([sys.executable, '-c', 'import update_apps; print(update_apps.VERSION)'],
                                cwd=self.root, check=True, capture_output=True, text=True)
        self.assertEqual(result.stdout.strip(), '1.5.4')
