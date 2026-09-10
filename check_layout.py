from contextlib import nullcontext
import sys
import threading
import tkinter as tk
from tkinter import font
from unittest.mock import patch
import update_apps as u
root = tk.Tk()
# Use the device's exact size on development machines with larger displays.
with patch.object(root, 'attributes') if '--windowed' in sys.argv else nullcontext():
    w = u.Window(root)
root.update()
for button in (w.check_button, w.install_button, w.home):
    assert button.winfo_rootx() >= root.winfo_rootx()
    assert button.winfo_rooty() >= root.winfo_rooty()
    assert button.winfo_rootx() - root.winfo_rootx() + button.winfo_width() <= 480
    assert button.winfo_rooty() - root.winfo_rooty() + button.winfo_height() <= 272
    f = font.Font(font=button['font'])
    assert f.measure(button['text']) + 12 < button.winfo_width()
assert str(w.install_button['state']) == 'disabled'

def press(key):
    modifiers, _, keysym = key.rpartition('-')
    prefix = modifiers + '-' if modifiers else ''
    if keysym.startswith('KP_') and root.tk.call('tk', 'windowingsystem') == 'aqua':
        # Aqua synthesizes keypad arrows as "??". Check the binding and exercise
        # its regular-key equivalent; unit tests also cover each keypad callback.
        assert root.focus_get().bind('<' + keysym + '>')
        keysym = 'Return' if keysym == 'KP_Enter' else keysym[3:]
    root.focus_get().event_generate('<' + prefix + 'KeyPress-' + keysym + '>')
    root.update()
    (root.focus_get() or root).event_generate('<' + prefix + 'KeyRelease-' + keysym + '>')
    root.update()

root.focus_force()
w.focus_navigation()
root.update()
assert root.focus_get() is w.list
assert w.list.focus() == '0'
assert w.list.selection() == ('0',)
assert not w.selected
press('Down')
assert w.list.focus() == '1'
assert not w.selected
press('Down')
assert root.focus_get() is w.check_button
press('Right')
assert root.focus_get() is w.home  # Disabled Install is skipped.
press('Tab')
assert root.focus_get() is w.list
press('Shift-Tab')
assert root.focus_get() is w.home
press('KP_Down')
assert root.focus_get() is w.list
assert w.list.focus() == '0'
press('KP_Down')
assert w.list.focus() == '1'
press('KP_Up')
assert w.list.focus() == '0'
press('Return')
assert w.selected == {0}
press('KP_Enter')
assert not w.selected
press('space')
assert w.selected == {0}
press('space')
assert not w.selected

w.results = {0: dict(needed=True, version='v1.0.0')}
w.events.put(('row', 0, 'cd1f1d7a', 'v1.0.0'))
w.events.put(('done', '1 update available. Close the app before installing.'))
w.poll()
root.update()
assert str(w.install_button['state']) == 'disabled'
w.toggle_index(0)
assert str(w.install_button['state']) == 'normal'
assert w.selected == {0}
w.toggle_index(0)
assert str(w.install_button['state']) == 'disabled'
w.toggle_index(0)
assert w.list.item('0')['values'][2] == 'v1.0.0'
press('KP_Right')
assert root.focus_get() is w.check_button
press('KP_Right')
assert root.focus_get() is w.install_button
press('KP_Left')
assert root.focus_get() is w.check_button
with patch.object(w, 'start') as start:
    press('Return')
    start.assert_called_once_with('check')
    start.reset_mock()
    press('Right')
    for key in ('Return', 'KP_Enter', 'space'):
        press(key)
        start.assert_called_once_with('install')
        start.reset_mock()
with patch.object(root, 'destroy') as close:
    press('Right')
    assert root.focus_get() is w.home
    press('KP_Enter')
    close.assert_called_once_with()

# Touch still toggles the checkbox and highlights the same row.
w.list.focus_set()
root.update()
x, y, width, height = w.list.bbox('1')
w.list.event_generate('<ButtonPress-1>', x=x + 70, y=y + height // 2)
w.list.event_generate('<ButtonRelease-1>', x=x + 70, y=y + height // 2)
root.update()
assert w.list.focus() == '1'
assert w.list.selection() == ('1',)
assert w.selected == {0, 1}
w.toggle_index(1)
w.busy = True
with patch.object(w, 'start') as start, patch.object(w, 'close') as close:
    for key in ('Down', 'KP_Down', 'Return', 'KP_Enter', 'space', 'Tab'):
        press(key)
    assert root.focus_get() is w.list
    assert w.list.focus() == '1'
    assert w.selected == {0}
    start.assert_not_called()
    close.assert_not_called()

for keys, expected in ((('Return',), False), (('KP_Right', 'KP_Enter'), True),
                       (('Tab', 'space'), True), (('Right', 'Left', 'space'), False),
                       (('Down', 'Up', 'Return'), False),
                       (('Right', 'Escape'), False), (('Home',), False)):
    answer, ready = [], threading.Event()
    w.show_close_prompt('Bitcoin CAD', answer, ready)
    root.update()
    dialog = root.grab_current()
    dialog.focus_lastfor().focus_force()
    root.update()
    assert root.focus_get()['text'] == 'Cancel'
    w.request_show()
    w.poll()
    root.update()
    assert root.focus_get()['text'] == 'Cancel'
    assert root.grab_current() is dialog
    for key in keys:
        press(key)
    assert answer == [expected]
    assert ready.is_set()
    assert root.grab_current() is None

w.results[0]['needed'] = False
w.events.put(('done', 'All apps are up to date.'))
w.poll()
assert str(w.install_button['state']) == 'disabled'
assert len(w.list.get_children()) == 2
w.restart_required = True
w.results[0]['needed'] = True
w.events.put(('done', 'Update Apps updated. Close and reopen it.'))
w.poll()
assert str(w.check_button['state']) == 'disabled'
assert str(w.install_button['state']) == 'disabled'
assert str(w.home['state']) == 'normal'
root.update()
assert root.focus_get() is w.home
for key in ('Up', 'Down', 'Left', 'Right', 'Tab', 'Shift-Tab', 'KP_Down'):
    press(key)
    assert root.focus_get() is w.home
root.destroy()
print('PASS: 480x272 layout, touch/keyboard/keypad navigation, modal confirmation, busy/restart states')
