"""Unit tests for YutoVNC launcher module and session/search/sorting behavior."""

import os
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import MagicMock, patch
from yutovnc.database import Database
from yutovnc.models import Host, HostStatus, AppSettings
from yutovnc.vnc_launcher import (
    build_viewer_command,
    find_viewer_path,
    normalize_scaling_mode,
    set_window_scaling,
    TIGHTVNC_CMD_SCALE_100,
    TIGHTVNC_CMD_SCALE_AUTO,
    WM_COMMAND,
    Session,
    SessionManager,
)
from yutovnc.ui.session_tab import SessionTab
from yutovnc.ui.main_window import MainWindow

class TestVncLauncher(unittest.TestCase):
    def test_build_tightvnc_command(self):
        host = Host(
            alias="PC Lab 01",
            ip="192.168.1.100",
            port=5900,
            view_only=True,
            fullscreen=False,
            scaling="auto"
        )
        cmd = build_viewer_command(r"C:\Program Files\TightVNC\tvnviewer.exe", host, "SecretPass")
        self.assertIn("-host=192.168.1.100", cmd)
        self.assertIn("-port=5900", cmd)
        self.assertIn("-password=SecretPass", cmd)
        self.assertIn("-viewonly=yes", cmd)
        self.assertIn("-fullscreen=no", cmd)
        self.assertIn("-scale=auto", cmd)

    def test_build_tightvnc_command_defaults_and_100(self):
        host_off = Host(alias="PC 2", ip="10.0.0.2", port=5900, view_only=False, scaling="100%")
        cmd = build_viewer_command(r"C:\Program Files\TightVNC\tvnviewer.exe", host_off, "")
        self.assertIn("-viewonly=no", cmd)
        self.assertIn("-scale=100", cmd)

        # 'none' or default scales to Fit (-scale=auto)
        host_none = Host(alias="PC 3", ip="10.0.0.3", port=5900, view_only=False, scaling="none")
        cmd_none = build_viewer_command(r"C:\Program Files\TightVNC\tvnviewer.exe", host_none, "")
        self.assertIn("-scale=auto", cmd_none)

    def test_session_termination_clears_handles(self):
        host = Host(id=1, alias="Test", ip="127.0.0.1")
        mock_proc = MagicMock()
        mock_proc.poll.side_effect = [None, 0]
        sess = Session(host, mock_proc, is_embedded=True)
        self.assertTrue(sess.is_scaled)

        mgr = SessionManager()
        mgr.sessions[sess.session_id] = sess
        mgr.close_session(sess.session_id)

        mock_proc.terminate.assert_called_once()
        self.assertTrue(sess._closed)
        self.assertIsNone(sess.proc)
        self.assertIsNone(sess.hwnd)
        self.assertNotIn(sess.session_id, mgr.sessions)

    def test_find_viewer_path(self):
        path = find_viewer_path()
        self.assertIsNotNone(path)
        self.assertTrue(path.endswith(".exe"))

    def test_normalize_scaling_mode(self):
        self.assertEqual(normalize_scaling_mode("auto"), "fit")
        self.assertEqual(normalize_scaling_mode("fit"), "fit")
        self.assertEqual(normalize_scaling_mode("none"), "fit")
        self.assertEqual(normalize_scaling_mode(""), "fit")
        self.assertEqual(normalize_scaling_mode("100%"), "100%")
        self.assertEqual(normalize_scaling_mode("100"), "100%")

    def test_set_window_scaling_idempotent(self):
        with patch("yutovnc.vnc_launcher.user32") as mock_user32, \
             patch("yutovnc.vnc_launcher.is_window_auto_scaled") as mock_is_auto:
            mock_user32.IsWindow.return_value = True

            # Already Auto-Scale ON -> must NOT re-post 214 (which would toggle it OFF)
            mock_is_auto.return_value = True
            self.assertTrue(set_window_scaling(12345, fit=True))
            mock_user32.PostMessageW.assert_not_called()

            # Currently 100% -> must post 214 to enable Auto-Scale
            mock_is_auto.return_value = False
            self.assertTrue(set_window_scaling(12345, fit=True))
            mock_user32.PostMessageW.assert_called_once_with(12345, WM_COMMAND, TIGHTVNC_CMD_SCALE_AUTO, 0)

            mock_user32.PostMessageW.reset_mock()
            # Switching from Auto-Scale to 100% -> must post 213
            mock_is_auto.return_value = True
            self.assertTrue(set_window_scaling(12345, fit=False))
            mock_user32.PostMessageW.assert_called_once_with(12345, WM_COMMAND, TIGHTVNC_CMD_SCALE_100, 0)

    def test_session_tab_preserves_scaling_on_view_only_toggle(self):
        root = tk.Tk()
        root.withdraw()
        try:
            nb = ttk.Notebook(root)
            host = Host(id=1, alias="Lab", ip="10.0.0.5", scaling="fit", view_only=False)
            sess = Session(host, None, is_embedded=True)
            captured = []

            def fake_reconnect(tab, view_only, is_scaled):
                captured.append((tab.current_scale_mode, view_only, is_scaled))

            tab = SessionTab(
                nb, sess, AppSettings(),
                on_close=lambda *_a: None,
                on_reconnect=lambda *_a: None,
                on_in_place_reconnect=fake_reconnect,
            )
            self.assertEqual(tab.current_scale_mode, "fit")
            self.assertIn("Fit", tab.scale_btn.cget("text"))

            # Toggle View-Only ON -> Fit must be preserved
            tab._action_toggle_view_only()
            self.assertEqual(captured[-1], ("fit", True, True))
            self.assertEqual(tab.current_scale_mode, "fit")

            # Switch to 100%, then toggle View-Only OFF -> 100% must be preserved
            tab._action_scale()
            self.assertEqual(tab.current_scale_mode, "100%")
            self.assertIn("100%", tab.scale_btn.cget("text"))
            tab._action_toggle_view_only()
            self.assertEqual(captured[-1], ("100%", False, False))
            self.assertEqual(tab.current_scale_mode, "100%")
            tab.destroy()
        finally:
            root.destroy()

    def test_clear_search_button_clears_text_and_restores_focus(self):
        app = MainWindow()
        try:
            app.update()
            # Search bar must live inside Address Book tab rather than top header
            self.assertTrue(str(app.search_entry).startswith(str(app.address_book_tab)))
            self.assertTrue(str(app.clear_search_btn).startswith(str(app.address_book_tab)))

            total_rows = len(app.host_tree.get_children())
            app.search_entry.focus_set()
            app.search_var.set("__nonexistent_host_query__")
            app.update()
            self.assertEqual(len(app.host_tree.get_children()), 0)

            app.clear_search_btn.invoke()
            app.update()
            self.assertEqual(app.search_var.get(), "")
            self.assertEqual(app.search_entry.get(), "")
            self.assertEqual(len(app.host_tree.get_children()), total_rows)
            self.assertIs(app.focus_get(), app.search_entry)
        finally:
            app.monitor.shutdown()
            app.destroy()

    def test_notebook_tab_switch_releases_and_restores_vnc_focus(self):
        app = MainWindow()
        try:
            app.update()
            mock_tab = MagicMock(spec=SessionTab)
            app.active_session_tabs["s1"] = mock_tab

            # Switch to Address Book tab -> release VNC focus and force Tk focus
            app.notebook.select(app.address_book_tab)
            with patch.object(app, "focus_force") as mock_focus_force:
                app._on_notebook_tab_changed()
                mock_tab.release_focus.assert_called_once()
                mock_focus_force.assert_called_once()

            # Clicking search entry also releases VNC focus and forces focus onto search_entry
            mock_tab.release_focus.reset_mock()
            with patch.object(app.search_entry, "focus_force") as mock_entry_force:
                app._on_search_entry_click()
                mock_tab.release_focus.assert_called_once()
                mock_entry_force.assert_called_once()
        finally:
            app.monitor.shutdown()
            app.destroy()

    def test_host_table_column_sorting_and_numeric_ip(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        app = None
        try:
            db = Database(db_path)
            h1 = Host(alias="PC-B", ip="10.40.104.10", port=5901, group="Lab")
            h2 = Host(alias="PC-A", ip="10.40.104.2", port=5900, group="Admin")
            h3 = Host(alias="PC-C", ip="192.168.1.5", port=5902, group="Lab")
            h1.id = db.add_host(h1)
            h2.id = db.add_host(h2)
            h3.id = db.add_host(h3)

            with patch("yutovnc.ui.main_window.Database", return_value=db):
                app = MainWindow()
                statuses = {
                    h1.id: HostStatus(host_id=h1.id, online=True, latency_ms=25.0),
                    h2.id: HostStatus(host_id=h2.id, online=False),
                    h3.id: HostStatus(host_id=h3.id, online=True, latency_ms=5.0),
                }
                app.monitor.get_status = lambda hid: statuses.get(hid)
                app.update()

                # Sort by IP ASC -> 10.40.104.2 before 10.40.104.10 before 192.168.1.5
                app._on_host_column_click("ip")
                ips_asc = [app.host_tree.item(iid, "values")[3] for iid in app.host_tree.get_children()]
                self.assertEqual(ips_asc, ["10.40.104.2", "10.40.104.10", "192.168.1.5"])
                self.assertTrue(app.host_tree.heading("ip", "text").endswith("▲"))

                # Sort by IP DESC
                app._on_host_column_click("ip")
                ips_desc = [app.host_tree.item(iid, "values")[3] for iid in app.host_tree.get_children()]
                self.assertEqual(ips_desc, ["192.168.1.5", "10.40.104.10", "10.40.104.2"])
                self.assertTrue(app.host_tree.heading("ip", "text").endswith("▼"))

                # Search and clear preserves active IP DESC sort order
                app.search_var.set("10.40.104")
                app.update()
                self.assertEqual(
                    [app.host_tree.item(iid, "values")[3] for iid in app.host_tree.get_children()],
                    ["10.40.104.10", "10.40.104.2"]
                )
                app.clear_search_btn.invoke()
                app.update()
                self.assertEqual(
                    [app.host_tree.item(iid, "values")[3] for iid in app.host_tree.get_children()],
                    ["192.168.1.5", "10.40.104.10", "10.40.104.2"]
                )

                # Sort by Port ASC and Status ASC
                app._on_host_column_click("port")
                self.assertEqual(
                    [app.host_tree.item(iid, "values")[4] for iid in app.host_tree.get_children()],
                    ["5900", "5901", "5902"]
                )
                self.assertEqual(app.host_tree.heading("ip", "text"), "IP Address")
                self.assertTrue(app.host_tree.heading("port", "text").endswith("▲"))

                app._on_host_column_click("status")
                aliases_by_status = [app.host_tree.item(iid, "values")[2] for iid in app.host_tree.get_children()]
                self.assertEqual(aliases_by_status, ["PC-C", "PC-B", "PC-A"])
        finally:
            if app is not None:
                app.monitor.shutdown()
                app.destroy()
            if os.path.exists(db_path):
                os.remove(db_path)

if __name__ == "__main__":
    unittest.main()
