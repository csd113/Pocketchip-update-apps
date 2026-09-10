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
        self.root = Path(self.temp.name).resolve()
        self.path = self.root / 'bitcoin.py'
        self.path.write_bytes(b'print("old")\n')
        (self.root / 'launch').write_text('#!/bin/sh\n')
        (self.root / 'launch').chmod(0o755)
        (self.root / 'bitcoin.png').write_bytes(b'fixture icon')
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

    def test_missing_app_check(self):
        self.path.unlink()
        result = self.result()
        self.assertTrue(result['needed'])
        self.assertIsNone(result['old'])
        self.assertEqual(u.installed(self.app), 'not installed')

    def test_up_to_date(self):
        self.path.write_bytes(self.data)
        self.assertFalse(self.result()['needed'])

    def test_matching_source_still_offers_support_file_repair(self):
        self.path.write_bytes(self.data)
        for name in ('launch', 'bitcoin.png'):
            with self.subTest(name=name):
                path = self.root / name
                old = path.read_bytes()
                mode = path.stat().st_mode & 0o777
                path.unlink()
                self.assertTrue(self.result()['needed'])
                self.assertEqual(u.installed(self.app), 'incomplete / repair')
                path.write_bytes(old)
                path.chmod(mode)

    def test_matching_source_with_pending_marker_needs_repair(self):
        self.path.write_bytes(self.data)
        (self.root / '.installation-pending').write_text('interrupted')
        self.assertTrue(self.result()['needed'])
        self.assertEqual(u.installed(self.app), 'incomplete / repair')

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


class CloseApps(unittest.TestCase):
    def setUp(self):
        self.app = dict(name='Bitcoin CAD', path=Path('/home/chip/bitcoin.py'))

    def test_only_confirmed_matching_process_gets_term(self):
        with patch.object(u, 'process_identity', side_effect=['old-start', 'reused']), \
                patch.object(u.os, 'kill') as kill, patch.object(u, 'running', return_value=False):
            u.close_app(self.app, {123: 'old-start', 456: 'previous'})
        kill.assert_called_once_with(123, u.signal.SIGTERM)

    def test_app_that_will_not_close_times_out(self):
        with patch.object(u, 'process_identity', return_value='start'), \
                patch.object(u.os, 'kill'), patch.object(u, 'running', return_value=True):
            with self.assertRaisesRegex(ValueError, 'Update skipped'):
                u.close_app(self.app, {123: 'start'}, timeout=0)

    def test_process_identity_rejects_other_commands(self):
        import os
        with tempfile.TemporaryDirectory() as temp:
            proc = Path(temp) / '123'
            proc.mkdir()
            (proc / 'stat').write_text('123 (python tricky ) name) ' + ' '.join(['S'] + ['0'] * 18 + ['999']))
            (proc / 'cmdline').write_bytes(b'/usr/bin/python3\0/home/chip/bitcoin.py\0')
            self.assertEqual(u.process_identity(proc, self.app), '999')
            (proc / 'cmdline').write_bytes(b'/bin/editor\0/home/chip/bitcoin.py\0')
            self.assertIsNone(u.process_identity(proc, self.app))
            (proc / 'cmdline').write_bytes(b'/usr/bin/python3\0other.py\0/home/chip/bitcoin.py\0')
            self.assertIsNone(u.process_identity(proc, self.app))

    def worker(self, approved, closing_error=None):
        import queue
        window = object.__new__(u.Window)
        window.results = {0: {'needed': True, 'version': 'v1.3.0'}}
        window.events = queue.Queue()
        window.restart_required = False
        order = []
        def confirm(app):
            order.append('prompt')
            return approved
        def close(app, processes):
            order.append('close')
            if closing_error:
                raise closing_error
        def install(app, result):
            order.append('install')
        with patch.object(u, 'APPS', [self.app]), \
                patch.object(u, 'running_processes', return_value={123: 'start'}), \
                patch.object(window, 'confirm_close', side_effect=confirm), \
                patch.object(u, 'close_app', side_effect=close), \
                patch.object(u, 'install', side_effect=install), \
                patch.object(u, 'installed', return_value='v1.3.0'):
            window.work('install', frozenset({0}))
        return order, window

    def test_cancel_neither_closes_nor_installs(self):
        order, window = self.worker(False)
        self.assertEqual(order, ['prompt'])
        self.assertTrue(window.results[0]['needed'])

    def test_confirm_closes_before_installing(self):
        order, window = self.worker(True)
        self.assertEqual(order, ['prompt', 'close', 'install'])
        self.assertFalse(window.results[0]['needed'])

    def test_close_failure_does_not_install(self):
        order, window = self.worker(True, ValueError('did not close'))
        self.assertEqual(order, ['prompt', 'close'])
        self.assertTrue(window.results[0]['needed'])

    def test_show_signal_does_not_lock_event_queue(self):
        import subprocess
        import sys
        script = '''
import queue
import signal
import update_apps as u
# Bound the lock-sensitive operation independently of slow ARM/Tk imports.
signal.alarm(2)
window = object.__new__(u.Window)
window.events = queue.Queue()
window.show_requested = False
with window.events.mutex:
    window.request_show()
assert window.show_requested
signal.alarm(0)
'''
        subprocess.run([sys.executable, '-c', script], cwd=Path(u.__file__).parent,
                       check=True, timeout=60, capture_output=True)


class Selection(unittest.TestCase):
    def window(self):
        import queue
        from unittest.mock import Mock
        window = object.__new__(u.Window)
        window.results = {0: dict(needed=True, version='v1.0.0'),
                          1: dict(needed=True, version='v1.4.0')}
        window.selected = set()
        window.busy = False
        window.restart_required = False
        window.events = queue.Queue()
        window.list = Mock()
        window.checkbox_images = ['empty', 'checked']
        window.install_button = Mock()
        window.check_button = Mock()
        window.home = Mock()
        window.status = Mock()
        return window

    def test_nothing_selected_cannot_start_install(self):
        window = self.window()
        with patch.object(u.threading, 'Thread') as thread:
            window.start('install')
        thread.assert_not_called()
        self.assertFalse(window.busy)

    def test_checkbox_controls_button_and_can_be_cleared(self):
        window = self.window()
        window.toggle_index(0)
        self.assertEqual(window.selected, {0})
        window.install_button.configure.assert_called_with(state='normal')
        window.toggle_index(0)
        self.assertEqual(window.selected, set())
        window.install_button.configure.assert_called_with(state='disabled')

    def test_current_checked_app_does_not_enable_install(self):
        window = self.window()
        window.results[0]['needed'] = False
        window.toggle_index(0)
        self.assertFalse(window.pending_selection())
        window.install_button.configure.assert_called_with(state='disabled')

    def test_busy_or_self_updated_window_cannot_change_selection(self):
        window = self.window()
        window.busy = True
        window.toggle_index(0)
        self.assertFalse(window.selected)
        window.busy = False
        window.restart_required = True
        window.toggle_index(0)
        self.assertFalse(window.selected)

    def test_worker_only_installs_snapshot_and_never_closes_unchecked_app(self):
        window = self.window()
        with patch.object(u, 'running_processes', return_value={}) as processes, \
                patch.object(u, 'install') as install, \
                patch.object(u, 'installed', return_value='v1.4.0'):
            window.work('install', frozenset({1}))
        install.assert_called_once_with(u.APPS[1], window.results[1])
        processes.assert_not_called()
        self.assertTrue(window.results[0]['needed'])
        self.assertTrue(window.restart_required)

    def test_bitcoin_only_does_not_update_self(self):
        window = self.window()
        with patch.object(u, 'running_processes', return_value={}), \
                patch.object(u, 'install') as install, \
                patch.object(u, 'installed', return_value='v1.1.0'):
            window.work('install', frozenset({0}))
        install.assert_called_once_with(u.APPS[0], window.results[0])
        self.assertTrue(window.results[1]['needed'])
        self.assertFalse(window.restart_required)

    def test_start_captures_immutable_selection(self):
        window = self.window()
        window.selected = {0}
        with patch.object(u.threading, 'Thread') as thread:
            window.start('install')
        self.assertEqual(thread.call_args.kwargs['args'], ('install', frozenset({0})))
        self.assertTrue(window.busy)


class Navigation(unittest.TestCase):
    def setUp(self):
        from unittest.mock import MagicMock, Mock
        self.window = Selection().window()
        self.window.root = Mock()
        self.window.root.grab_current.return_value = None
        self.window.root.focus_get.return_value = self.window.list
        self.window.list.get_children.return_value = ('0', '1')
        self.window.list.focus.return_value = '0'
        for name in ('home', 'check_button', 'install_button'):
            button = MagicMock()
            button.__getitem__.return_value = 'normal'
            setattr(self.window, name, button)

    def test_keypad_and_keyboard_bindings_dispatch_once(self):
        from unittest.mock import Mock
        widget, move, activate = Mock(), Mock(return_value='break'), Mock(return_value='break')
        u.bind_navigation(widget, move, activate)
        bindings = dict(call.args for call in widget.bind.call_args_list)
        for keys, step, vertical in (
                (('Up', 'KP_Up'), -1, True), (('Down', 'KP_Down'), 1, True),
                (('Left', 'KP_Left', 'Shift-Tab', 'ISO_Left_Tab'), -1, False),
                (('Right', 'KP_Right', 'Tab'), 1, False)):
            for key in keys:
                with self.subTest(key=key):
                    self.assertEqual(bindings['<' + key + '>'](None), 'break')
                    move.assert_called_once_with(step, vertical)
                    move.reset_mock()
        for key in ('Return', 'KP_Enter', 'space'):
            with self.subTest(key=key):
                self.assertEqual(bindings['<' + key + '>'](None), 'break')
                activate.assert_called_once_with(None)
                activate.reset_mock()

    def test_row_navigation_highlights_without_checking(self):
        self.assertEqual(self.window.move_focus(1), 'break')
        self.window.list.focus.assert_called_with('1')
        self.window.list.selection_set.assert_called_once_with('1')
        self.window.list.see.assert_called_once_with('1')
        self.assertEqual(self.window.selected, set())

    def test_leaving_and_entering_list_at_each_end(self):
        w = self.window
        w.move_focus(-1)
        w.home.focus_set.assert_called_once_with()
        w.list.focus.return_value = '1'
        w.move_focus(1)
        w.check_button.focus_set.assert_called_once_with()
        w.root.focus_get.return_value = w.check_button
        w.move_focus(-1)
        w.list.focus.assert_called_with('1')
        w.list.focus_set.assert_called_once_with()

    def test_disabled_install_is_skipped_and_navigation_wraps(self):
        w = self.window
        w.install_button.__getitem__.return_value = 'disabled'
        w.root.focus_get.return_value = w.check_button
        w.move_focus(1, False)
        w.home.focus_set.assert_called_once_with()
        w.install_button.focus_set.assert_not_called()
        w.root.focus_get.return_value = w.home
        w.move_focus(-1, False)
        w.check_button.focus_set.assert_called_once_with()

    def test_busy_navigation_and_activation_do_nothing(self):
        w = self.window
        w.busy = True
        w.move_focus(1)
        w.activate_focused(None)
        w.root.focus_get.return_value = w.check_button
        w.activate_focused(None)
        self.assertFalse(w.selected)
        w.list.selection_set.assert_not_called()
        w.check_button.focus_set.assert_not_called()
        w.check_button.invoke.assert_not_called()

    def test_activation_toggles_row_or_invokes_focused_button(self):
        w = self.window
        w.activate_focused(None)
        self.assertEqual(w.selected, {0})
        w.activate_focused(None)
        self.assertEqual(w.selected, set())
        w.root.focus_get.return_value = w.check_button
        w.activate_focused(None)
        w.check_button.invoke.assert_called_once_with()

    def test_self_update_leaves_only_home_reachable(self):
        w = self.window
        w.restart_required = True
        w.activate_focused(None)
        self.assertFalse(w.selected)
        w.focus_navigation()
        w.home.focus_set.assert_called_once_with()
        w.move_focus(1)
        self.assertEqual(w.navigation_widgets(), (w.home,))
        self.assertEqual(w.home.focus_set.call_count, 2)

    def test_returning_to_window_preserves_modal_focus(self):
        from unittest.mock import Mock
        w = self.window
        dialog = Mock()
        w.root.grab_current.return_value = dialog
        w.focus_navigation(force=True)
        dialog.lift.assert_called_once_with()
        dialog.focus_lastfor.return_value.focus_force.assert_called_once_with()
        w.list.focus_force.assert_not_called()


class LauncherLifetime(unittest.TestCase):
    @unittest.skipUnless(Path('/proc/self/cmdline').exists(), 'Linux process identity check')
    def test_second_launcher_waits_until_existing_app_closes(self):
        import subprocess
        import sys
        import time
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            owner_script = '''
import fcntl
import os
from pathlib import Path
import signal
import sys
import time
root = Path(sys.argv[2])
signal.signal(signal.SIGUSR1, lambda *_: (root / 'shown').touch())
with (root / 'updater.lock').open('a+') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    lock.write(str(os.getpid()))
    lock.flush()
    (root / 'ready').touch()
    while not (root / 'stop').exists():
        time.sleep(0.02)
'''
            child_script = '''
from pathlib import Path
import sys
import update_apps as u
u.DATA = Path(sys.argv[1])
u.main()
'''
            owner = subprocess.Popen([sys.executable, '-c', owner_script,
                                      str(Path(u.__file__).resolve()), temp])
            child = None
            def await_file(name):
                deadline = time.monotonic() + 60
                while not (data / name).exists():
                    if time.monotonic() >= deadline:
                        self.fail('Timed out waiting for ' + name)
                    time.sleep(0.02)
            try:
                await_file('ready')
                child = subprocess.Popen([sys.executable, '-c', child_script, temp],
                                         cwd=Path(u.__file__).parent)
                await_file('shown')
                with self.assertRaises(subprocess.TimeoutExpired):
                    child.wait(timeout=1)
                (data / 'stop').touch()
                self.assertEqual(owner.wait(timeout=10), 0)
                self.assertEqual(child.wait(timeout=10), 0)
            finally:
                for process in (child, owner):
                    if process is not None and process.poll() is None:
                        process.terminate()
                        process.wait(timeout=10)
