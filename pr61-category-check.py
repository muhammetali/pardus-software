#!/usr/bin/env python3
"""Compile PR translations and render actual category rows in GTK.

Usage: xvfb-run -a python3 pr61-category-check.py REPOSITORY CATS_JSON OUTPUT_DIR
Run in a Turkish UTF-8 locale. Does not install translations or start the app.
"""
import json
import locale
import logging
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace

repository, cats_file, output = map(Path, sys.argv[1:])
output.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(repository / 'src'))
import MainWindow
from gi.repository import Gdk, GLib, Gtk


def flush():
    context = GLib.MainContext.default()
    while context.pending():
        context.iteration(False)


with tempfile.TemporaryDirectory(prefix='pardus-category-review-') as tmp:
    translations = Path(tmp) / 'tr/LC_MESSAGES'
    translations.mkdir(parents=True)
    subprocess.run(['msgfmt', '--check', '-o', str(translations / 'pardus-software.mo'),
                    str(repository / 'po/tr.po')], check=True)
    locale.bindtextdomain('pardus-software', tmp)
    assert locale.setlocale(locale.LC_MESSAGES).startswith('tr_TR'), 'Use LC_ALL=tr_TR.UTF-8'
    window = MainWindow.MainWindow.__new__(MainWindow.MainWindow)
    window.Logger = logging.getLogger('review')
    window.Server = SimpleNamespace(connection=True)
    window.user_locale = window.get_user_locale()
    window.cats = json.loads(cats_file.read_text())['categories']
    window.cat_all = {'name': 'tümü', 'icon': 'all'}
    window.server_cat_all = {}
    window.ui_leftcats_listbox = Gtk.ListBox()
    window.ui_leftinstalled_listbox = Gtk.ListBox()
    window.set_categories()
    flush()
    labels = [row.get_child().get_children()[1].get_text()
              for row in window.ui_leftcats_listbox.get_children()]
    results = {'locale': locale.setlocale(locale.LC_MESSAGES), 'labels': labels,
               'all': window.get_category_display_name('tümü'),
               'internet': window.get_category_display_name('internet')}
    results['passed'] = results['all'] == 'Tümü' and results['internet'] == 'İnternet'
    # Show the real set_categories() output in a small test window. This is a
    # category-rendering check, not a full-application screenshot.
    preview = Gtk.Window(title='PR #61 — kategori kontrolü')
    preview.set_default_size(320, 520)
    preview.add(window.ui_leftcats_listbox)
    preview.show_all()
    loop = GLib.MainLoop()

    def capture():
        surface = preview.get_window()
        pixbuf = Gdk.pixbuf_get_from_window(surface, 0, 0, surface.get_width(), surface.get_height())
        pixbuf.savev(str(output / 'categories.png'), 'png', [], [])
        loop.quit()
        return False

    GLib.timeout_add(300, capture)
    loop.run()
    preview.destroy()
    (output / 'result.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(results, ensure_ascii=False, indent=2))
    sys.exit(0 if results['passed'] else 1)
