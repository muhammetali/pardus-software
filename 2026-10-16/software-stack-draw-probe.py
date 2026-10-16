#!/usr/bin/env python3
"""Exercise visible GTK navigation and retain the call stack of drawing errors."""
import importlib.util
from pathlib import Path
import sys
import time
import traceback
from types import SimpleNamespace

root = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location('offline_tests', root/'tests/offline_navigation.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Gtk, GLib = module.Gtk, module.GLib
errors=[]
def on_log(domain, level, message, data):
    errors.append(message)
    print('GTK_CRITICAL', message, ''.join(traceback.format_stack()), flush=True)
handler=GLib.log_set_handler('Gtk', GLib.LogLevelFlags.LEVEL_CRITICAL, on_log, None)
test=module.OfflineNavigationTests()
test.setUp()
w=test.window
w.display_width=1280
w.UserSettings=SimpleNamespace(config_animations=True)
w.set_animations()
def settle(seconds=0.6):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        test.flush_events()
        time.sleep(0.01)
try:
    widgets=[]
    for n in range(100):
        app={'id':f'test-{n}.desktop', 'name':f'Application {n}', 'icon_name':'application-x-executable',
             'description':'Test application', 'filename':f'/usr/share/applications/test-{n}.desktop',
             'keywords':'', 'executable':'true', 'disk_usage':0, 'package_name':'-'}
        widgets.append(w.create_myapp_widget(app))
    test.flush_events()
    for widget in widgets:
        w.ui_installedapps_flowbox.add(widget)
    settle()
    w.ui_installedapps_flowbox.show_all()
    w.MainWindow.show()
    test.show_home()
    settle()
    w.GtkBuilder.get_object('offline_installed_button').clicked()
    settle()
    w.ui_top_searchentry.set_text('Application 99')
    settle()
    rows=w.ui_installedapps_flowbox.get_children()
    selected=[r for r in rows if r.get_child_visible()]
    assert len(selected)==1
    def children(widget):
        yield widget
        if isinstance(widget,Gtk.Container):
            for child in widget.get_children():
                yield from children(child)
    remove=[v for v in children(selected[0]) if isinstance(v,Gtk.Button)
            and isinstance(getattr(v,'name',None),dict)][0]
    w.myapp_toremove='test-99'
    w.isinstalled=True
    w.isupgrade=False
    w.ui_myapp_pop_stack.set_visible_child_name('details')
    w.ui_myapp_details_popover.set_relative_to(remove)
    w.ui_myapp_details_popover.popup()
    settle()
    w.control_myapps('test-99','/usr/share/applications/test-99.desktop',0,False,True)
    settle()
    w.ui_top_searchentry.set_text('')
    settle()
    print('BACK',flush=True)
    w.ui_back_button.clicked()
    settle()
    print('RESULT',errors,'CALLBACK_COUNT',len(test.callback_errors),flush=True)
finally:
    try:
        test.tearDown()
    finally:
        print('CALLBACKS_FINAL',len(test.callback_errors),test.callback_errors[:1],flush=True)
        test.doCleanups()
        GLib.log_remove_handler('Gtk',handler)
assert not errors, errors
