#!/usr/bin/env python3
"""Kurulu uygulamayı gerçek GTK döngüsünde açıp arayüz akışını ölçer.

PARDUS_LAB_MODE: baseline, offline, online, restricted veya broken.
PARDUS_LAB_RESULT: JSON ve ekran görüntülerinin dosya öneki.
PARDUS_LAB_RECOVER=1: çevrimdışı akıştan sonra laboratuvar nft tablosunu
kaldırıp gerçek Tekrar Dene düğmesiyle bağlantının geri gelmesini doğrular.
Uygulamanın metotları, ağ istemcisi ve paket listesi değiştirilmez.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkX11", "3.0")
from gi.repository import Gdk, GdkX11, GLib, Gtk

MODE = os.environ.get("PARDUS_LAB_MODE", "baseline")
PREFIX = Path(os.environ["PARDUS_LAB_RESULT"])
RECOVER = os.environ.get("PARDUS_LAB_RECOVER") == "1"
CHECK_SETTINGS = os.environ.get("PARDUS_LAB_SETTINGS") == "1"
REMOVE_FIXTURE = os.environ.get("PARDUS_LAB_REMOVE") == "1"
FIXTURE = "pardus-offline-removal-test"
FIXTURE_DESKTOP = FIXTURE + ".desktop"
if REMOVE_FIXTURE:
    assert Path("/etc/hostname").read_text().strip() in ("pardus-domain-lab", "pardus-software23-lab")
    assert subprocess.check_output(["dpkg-query", "-W", "-f=${Status}", FIXTURE], text=True) == "install ok installed"
START = time.monotonic()
report = {"mode": MODE, "remove_fixture": REMOVE_FIXTURE, "steps": [],
          "desktop": os.environ.get("XDG_CURRENT_DESKTOP"),
          "session_type": os.environ.get("XDG_SESSION_TYPE"),
          "os_release": Path("/etc/os-release").read_text()}
phase = "startup"
next_action = 0
finished = False
ready_since = None
observed_phase = None
phase_started = START
callback_errors = []
sys.excepthook = lambda *error: callback_errors.append("".join(traceback.format_exception(*error)))
if os.environ.get("PARDUS_LAB_TRACE_DRAW") == "1":
    def trace_gtk(domain, level, message, data):
        print("GTK_DRAW_TRACE", message, "".join(traceback.format_stack()), flush=True)
        GLib.log_default_handler(domain, level, message, None)
    GLib.log_set_handler("Gtk", GLib.LogLevelFlags.LEVEL_CRITICAL, trace_gtk, None)


def record(name, **values):
    step = {"step": name, "seconds": round(time.monotonic() - START, 2), **values}
    report["steps"].append(step)
    print("EVIDENCE " + json.dumps(step, ensure_ascii=False), flush=True)


def screenshot(window, suffix):
    gdk_window = window.MainWindow.get_window()
    pixbuf = Gdk.pixbuf_get_from_window(
        gdk_window, 0, 0, gdk_window.get_width(), gdk_window.get_height())
    pixbuf.savev(str(PREFIX) + "-" + suffix + ".png", "png", [], [])
    if suffix in ("installed", "remove-confirm", "removed"):
        root = Gdk.get_default_root_window()
        pixbuf = Gdk.pixbuf_get_from_window(root, 0, 0, root.get_width(), root.get_height())
        pixbuf.savev(str(PREFIX) + "-" + suffix + "-desktop.png", "png", [], [])


def children(widget):
    yield widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            yield from children(child)


def activate(button):
    # clicked() tek başına fare tıklamasının odak değişimini üretmez.
    button.grab_focus()
    button.clicked()


def finish(app, status, error=None):
    global finished
    finished = True
    report.update(status=status, error=error)
    Path(str(PREFIX) + ".json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    app.quit()
    return False


def tick():
    global phase, next_action, ready_since, observed_phase, phase_started
    module = sys.modules.get("Main")
    app = getattr(module, "app", None)
    window = getattr(app, "window", None)
    if window is None:
        return True
    try:
        assert not callback_errors, callback_errors
        if phase != observed_phase:
            observed_phase, phase_started = phase, time.monotonic()
        phase_limit = 150 if phase in ("startup", "retry", "remove_wait") else 30
        assert time.monotonic() - phase_started < phase_limit, "Timed out waiting for " + phase
        if time.monotonic() - START > 300:
            raise AssertionError("Arayüz senaryosu 300 saniyede tamamlanmadı")
        if time.monotonic() < next_action:
            return True
        rows = window.ui_installedapps_flowbox.get_children()
        if phase in ("startup", "retry"):
            if window.mainstack.get_visible_child_name() != "home" or not rows:
                ready_since = None
                return True
            if window.mainstack.get_transition_running() or window.homestack.get_transition_running():
                ready_since = None
                return True
            if not window.MainWindow.is_active():
                xid = GdkX11.X11Window.get_xid(window.MainWindow.get_window())
                subprocess.run(["xdotool", "windowactivate", "--sync", str(xid)], check=True, timeout=5)
                ready_since = None
                return True
            # GTK state can change before the compositor paints the new page.
            # Allow a stable, focused page to be drawn before capture or hit testing.
            if ready_since is None:
                ready_since = time.monotonic()
                return True
            if time.monotonic() - ready_since < 0.5:
                return True
            record(phase, connected=window.Server.connection,
                   home=window.homestack.get_visible_child_name(),
                   page=window.ui_right_stack.get_visible_child_name(),
                   installed_count=len(rows), search_sensitive=window.ui_top_searchentry.get_sensitive(),
                   broken=window.isbroken)
            screenshot(window, phase)
            if phase == "retry":
                assert window.Server.connection
                assert window.homestack.get_visible_child_name() == "pardushome"
                assert window.ui_top_searchentry.get_sensitive()
                return finish(app, "passed")
            if MODE == "baseline":
                assert not window.Server.connection
                assert window.homestack.get_visible_child_name() == "noserver"
                assert not window.ui_top_searchentry.get_sensitive()
                assert window.GtkBuilder.get_object("offline_installed_button") is None
                return finish(app, "passed")
            if MODE in ("restricted", "broken"):
                assert not window.Server.connection
                assert window.homestack.get_visible_child_name() == "noserver"
                if MODE == "restricted":
                    assert window.myapps_perm == 0
                else:
                    assert window.isbroken and window.Package.cache.broken_count > 0
                button = window.GtkBuilder.get_object("offline_installed_button")
                assert button.get_mapped() and not button.get_sensitive()
                record(MODE, button_sensitive=False, myapps_permission=window.myapps_perm,
                       broken_count=window.Package.cache.broken_count)
                return finish(app, "passed")
            if MODE == "offline":
                assert not window.Server.connection
                button = window.GtkBuilder.get_object("offline_installed_button")
                assert button.get_mapped() and button.get_sensitive()
                # Gerçek bir fare tıklaması, GTK sinyali elle çağrılmıyor.
                x, y = button.translate_coordinates(window.MainWindow, 0, 0)
                _, root_x, root_y = window.MainWindow.get_window().get_origin()
                record("offline_button_target", x=root_x + x, y=root_y + y,
                       width=button.get_allocated_width(), height=button.get_allocated_height(),
                       focused=window.MainWindow.is_active())
                button.connect("clicked", lambda _button: record("offline_button_clicked"))
                subprocess.run(["xdotool", "mousemove", str(root_x + x + button.get_allocated_width() // 2),
                                str(root_y + y + button.get_allocated_height() // 2), "click", "1"], check=True)
            else:
                assert window.Server.connection
                installed_row = window.ui_leftinstalled_listbox.get_row_at_index(0)
                assert installed_row is not None
                window.ui_leftinstalled_listbox.emit("row-activated", installed_row)
            phase = "installed"
        elif phase == "installed":
            if window.ui_right_stack.get_visible_child_name() != "installed":
                return True
            assert window.homestack.get_visible_child_name() == "pardushome"
            assert window.ui_right_stack.get_visible_child_name() == "installed"
            assert window.ui_top_searchentry.get_sensitive()
            if MODE == "offline":
                assert not window.ui_upgradableapps_box.get_visible()
                assert not window.ui_upgradableapps_flowbox.get_visible()
                assert not window.ui_leftcats_box.get_visible()
            record("installed", count=len(rows), back_sensitive=window.ui_back_button.get_sensitive())
            screenshot(window, "installed")
            if CHECK_SETTINGS:
                window.ui_headermenu_popover.popup()
                activate(window.GtkBuilder.get_object("menu_settings"))
                phase = "settings"
            else:
                window.ui_top_searchentry.grab_focus()
                window.ui_top_searchentry.set_text("mousepad")
                phase = "search"
        elif phase == "settings":
            assert window.ui_right_stack.get_visible_child_name() == "settings"
            assert window.homestack.get_visible_child_name() == "pardushome"
            assert window.ui_top_searchentry.get_sensitive() == (MODE == "online")
            record("settings", page="settings", search_sensitive=window.ui_top_searchentry.get_sensitive())
            screenshot(window, "settings")
            activate(window.ui_back_button)
            phase = "settings_back"
        elif phase == "settings_back":
            assert window.ui_right_stack.get_visible_child_name() == "installed"
            assert window.ui_top_searchentry.get_sensitive()
            record("settings_back", page="installed")
            window.ui_top_searchentry.grab_focus()
            window.ui_top_searchentry.set_text("mousepad")
            phase = "search"
        elif phase == "search":
            visible = [row for row in rows if row.get_child_visible()]
            if not 0 < len(visible) < len(rows):
                return True
            assert 0 < len(visible) < len(rows), (len(visible), len(rows))
            record("search", query="mousepad", visible=len(visible), total=len(rows))
            screenshot(window, "search")
            matching = [widget for row in visible for widget in children(row)
                        if isinstance(widget, Gtk.ListBoxRow)
                        and isinstance(getattr(widget, "name", None), dict)
                        and widget.name.get("id") == "org.xfce.mousepad.desktop"]
            assert len(matching) == 1
            matching[0].grab_focus()
            matching[0].get_parent().emit("row-activated", matching[0])
            phase = "details"
        elif phase == "details":
            if window.ui_right_stack.get_visible_child_name() != "appdetails":
                return True
            phase = "details_ready"
        elif phase == "details_ready":
            assert window.ui_top_searchentry.get_sensitive() == (MODE == "online")
            record("details", page="appdetails", search_sensitive=window.ui_top_searchentry.get_sensitive())
            screenshot(window, "details")
            activate(window.ui_back_button)
            phase = "details_back"
        elif phase == "details_back":
            assert window.ui_right_stack.get_visible_child_name() == "installed"
            assert window.ui_top_searchentry.get_sensitive()
            record("details_back", page="installed")
            buttons = [widget for row in rows for widget in children(row)
                       if isinstance(widget, Gtk.Button) and getattr(widget, "name", None) == "org.xfce.mousepad.desktop"]
            assert len(buttons) == 1
            assert subprocess.run(["pgrep", "-x", "mousepad"], stdout=subprocess.DEVNULL).returncode != 0
            activate(buttons[0])
            phase = "launch"
        elif phase == "launch":
            if subprocess.run(["pgrep", "-x", "mousepad"], stdout=subprocess.DEVNULL).returncode != 0:
                return True
            record("launch", application="mousepad", running=True)
            subprocess.run(["pkill", "-x", "mousepad"], check=True)
            window.MainWindow.present()
            if REMOVE_FIXTURE:
                window.ui_top_searchentry.grab_focus()
                window.ui_top_searchentry.set_text("Offline Removal Test")
                phase = "remove_search"
                next_action = time.monotonic() + 1
                return True
            if MODE == "offline":
                # Geri dönüşle aynı anda gecikmiş search-changed sinyali gelsin.
                window.ui_top_searchentry.set_text("")
            activate(window.ui_back_button)
            phase = "back"
        elif phase == "remove_search":
            matches = [widget for row in rows if row.get_child_visible() for widget in children(row)
                       if isinstance(widget, Gtk.Button) and isinstance(getattr(widget, "name", None), dict)
                       and widget.name.get("id") == FIXTURE_DESKTOP]
            if not matches:
                return True
            assert len(matches) == 1, [(getattr(w, "name", None)) for w in matches]
            record("remove_selected", package=FIXTURE, installed_count=len(rows))
            activate(matches[0])
            phase = "remove_confirm"
        elif phase == "remove_confirm":
            if window.ui_myapp_pop_stack.get_visible_child_name() != "details":
                return True
            if window.ui_myapp_pop_stack.get_transition_running():
                return True
            phase = "remove_confirm_ready"
        elif phase == "remove_confirm_ready":
            assert window.myapp_toremove == FIXTURE
            assert window.myapp_toremove_list == [FIXTURE], window.myapp_toremove_list
            assert window.ui_myapp_pop_uninstall_button.get_sensitive()
            screenshot(window, "remove-confirm")
            record("remove_confirm", packages=window.myapp_toremove_list)
            activate(window.ui_myapp_pop_uninstall_button)
            phase = "remove_wait"
        elif phase == "remove_wait":
            if window.inprogress or window.queue:
                return True
            result = subprocess.run(["dpkg-query", "-W", "-f=${Status}", FIXTURE], capture_output=True, text=True)
            assert result.returncode == 1, (result.returncode, result.stdout, result.stderr)
            assert not Path("/usr/share/applications/" + FIXTURE_DESKTOP).exists()
            assert not [w for row in rows for w in children(row)
                        if isinstance(getattr(w, "name", None), dict) and w.name.get("id") == FIXTURE_DESKTOP]
            assert window.Package.cache.broken_count == 0
            removed = next(s for s in report["steps"] if s["step"] == "remove_selected")
            assert len(rows) == removed["installed_count"] - 1
            record("removed", package=FIXTURE, dpkg_query_exit=result.returncode,
                   desktop_file_exists=False, installed_count=len(rows), broken_count=0,
                   network_connected=window.Server.connection)
            phase = "remove_popup_closed"
        elif phase == "remove_popup_closed":
            if window.ui_myapp_details_popover.get_visible():
                return True
            window.ui_top_searchentry.set_text("")
            phase = "remove_done"
        elif phase == "remove_done":
            screenshot(window, "removed")
            activate(window.ui_back_button)
            phase = "back"
        elif phase == "back":
            expected = "noserver" if MODE == "offline" else "pardushome"
            assert window.homestack.get_visible_child_name() == expected
            assert window.ui_right_stack.get_visible_child_name() == "discover"
            assert window.ui_top_searchentry.get_sensitive() == (MODE == "online")
            record("back", home=expected, search_sensitive=window.ui_top_searchentry.get_sensitive())
            screenshot(window, "back")
            if RECOVER:
                subprocess.run(["sudo", "nft", "delete", "table", "inet", "codex_pardus_lab"], check=True)
                activate(window.GtkBuilder.get_object("retrybutton"))
                phase = "retry"
                ready_since = None
            else:
                return finish(app, "passed")
        next_action = time.monotonic() + 1
    except Exception:
        error = traceback.format_exc()
        print(error, flush=True)
        screenshot(window, "failure")
        return finish(app, "failed", error)
    return True


PREFIX.parent.mkdir(parents=True, exist_ok=True)
source = "/usr/share/pardus/pardus-software/src"
os.chdir(source)
sys.path.insert(0, source)
sys.argv = [source + "/Main.py"]
GLib.timeout_add(250, tick)
import Main  # noqa: E402 -- uygulamanın gerçek ana döngüsü
if not finished or report.get("status") != "passed":
    sys.exit(1)
