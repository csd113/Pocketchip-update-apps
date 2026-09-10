import tkinter as tk
from tkinter import font
from unittest.mock import patch
import update_apps as u
root = tk.Tk()
w = u.Window(root)
root.update()
for button in (w.check_button, w.install_button, w.home):
    assert button.winfo_rootx() >= 0
    assert button.winfo_rooty() >= 0
    assert button.winfo_rootx() + button.winfo_width() <= 480
    assert button.winfo_rooty() + button.winfo_height() <= 272
    f = font.Font(font=button['font'])
    assert f.measure(button['text']) + 12 < button.winfo_width()
assert str(w.install_button['state']) == 'disabled'
w.results = {0: dict(needed=True, version='v1.0.0')}
w.events.put(('row', 0, 'cd1f1d7a', 'v1.0.0'))
w.events.put(('done', '1 update available. Close the app before installing.'))
w.poll()
root.update()
assert str(w.install_button['state']) == 'normal'
assert w.list.item('0')['values'][2] == 'v1.0.0'
w.results[0]['needed'] = False
w.events.put(('done', 'All apps are up to date.'))
w.poll()
assert str(w.install_button['state']) == 'disabled'
root.destroy()
print('PASS: 480x272 layout, version row, install button states')
