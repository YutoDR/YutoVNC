"""Embedded Remote Session Tab with Quick Toolbar for YutoVNC."""

import tkinter as tk
from tkinter import ttk, messagebox
import os
from datetime import datetime
from typing import Optional, Callable
from yutovnc.models import Host, AppSettings
from yutovnc.vnc_launcher import (
    Session,
    normalize_scaling_mode,
    send_cad_to_window,
    capture_window_screenshot,
    resize_embedded_window,
    focus_embedded_window,
    set_window_scaling,
    user32,
    GWL_STYLE,
    WS_POPUP,
    WS_CAPTION,
    WS_THICKFRAME,
    WS_CHILD,
    SWP_FRAMECHANGED,
    SWP_SHOWWINDOW
)
from yutovnc.theme import get_theme_colors

class SessionTab(ttk.Frame):
    def __init__(
        self,
        parent: ttk.Notebook,
        session: Session,
        settings: AppSettings,
        on_close: Callable[["SessionTab", bool], None],
        on_reconnect: Callable[[Host], None],
        on_in_place_reconnect: Optional[Callable[["SessionTab", bool, bool], None]] = None,
        theme_name: str = "dark"
    ):
        super().__init__(parent, style="Surface.TFrame")
        self.notebook = parent
        self.session = session
        self.settings = settings
        self.on_close = on_close
        self.on_reconnect = on_reconnect
        self.on_in_place_reconnect = on_in_place_reconnect
        self.colors = get_theme_colors(theme_name)

        self._view_only_active = session.host.view_only
        self.current_scale_mode: str = normalize_scaling_mode(session.host.scaling)
        self.session.is_scaled = (self.current_scale_mode == "fit")
        self._is_closing = False
        self._popped_out = False
        self._reconnecting = False
        self._poll_after_id: Optional[str] = None
        self._toast_after_id: Optional[str] = None
        self._scale_after_ids: list[str] = []

        self._init_ui()
        self.bind("<Destroy>", self._on_widget_destroy)
        self._poll_after_id = self.after(1500, self._start_poll_alive)

    def _init_ui(self):
        # 1. Quick Toolbar at the top
        toolbar = ttk.Frame(self, style="Sidebar.TFrame", padding=(10, 6))
        toolbar.pack(fill="x", side="top")

        # Host Info Label
        info_text = f"🖥️ {self.session.host.alias} ({self.session.host.ip}:{self.session.host.port})"
        ttk.Label(toolbar, text=info_text, font=("Segoe UI", 10, "bold"), style="Surface.TLabel").pack(side="left", padx=(4, 16))

        # Toolbar Action Buttons
        ttk.Button(toolbar, text="⚡ Ctrl+Alt+Del", command=self._action_cad).pack(side="left", padx=2)
        ttk.Button(toolbar, text="📸 Screenshot", command=self._action_screenshot).pack(side="left", padx=2)

        # Two-way Scale toggle button (Default: Scale: Fit)
        self.scale_btn = ttk.Button(toolbar, text="🔲 Scale: Fit", style="Primary.TButton", command=self._action_scale)
        self.scale_btn.pack(side="left", padx=2)
        self._sync_scale_btn()

        # Live View-Only toggle with clear color indicator
        self.view_btn = ttk.Button(toolbar, text="👁️ View-Only: OFF", command=self._action_toggle_view_only)
        self.view_btn.pack(side="left", padx=2)
        self._sync_view_btn()

        # Reconnect & Pop out
        ttk.Button(toolbar, text="🔄 Reconnect", command=self._action_reconnect).pack(side="left", padx=2)
        ttk.Button(toolbar, text="↗️ Pop Out", command=self._action_pop_out).pack(side="left", padx=2)

        # Disconnect button (Danger style on right)
        ttk.Button(toolbar, text="❌ Disconnect", style="Danger.TButton", command=self._action_disconnect).pack(side="right", padx=4)

        # Status notification label inside toolbar
        self.status_lbl = ttk.Label(toolbar, text="Menghubungkan ke remote...", style="SurfaceMuted.TLabel")
        self.status_lbl.pack(side="right", padx=10)

        # 2. Container Frame for the embedded Win32 VNC window
        self.container = tk.Frame(self, bg="#000000", takefocus=True)
        self.container.pack(fill="both", expand=True)
        self.container.bind("<Configure>", self._on_container_resize)
        self.container.bind("<Button-1>", lambda _e: self.after(15, self.focus_vnc))
        self.container.bind("<FocusIn>", lambda _e: self.after(15, self.focus_vnc))

    def _sync_scale_btn(self):
        if self.current_scale_mode == "fit":
            self.scale_btn.configure(text="🔲 Scale: Fit", style="Primary.TButton")
        else:
            self.scale_btn.configure(text="🔍 Scale: 100% (Original)", style="TButton")

    def _sync_view_btn(self):
        if self._view_only_active:
            self.view_btn.configure(text="👁️ View-Only: ON", style="Warning.TButton")
        else:
            self.view_btn.configure(text="👁️ View-Only: OFF", style="TButton")

    def get_container_hwnd(self) -> int:
        self.notebook.update_idletasks()
        self.update_idletasks()
        return self.container.winfo_id()

    def get_container_size(self) -> tuple:
        self.notebook.update_idletasks()
        self.update_idletasks()
        w = self.container.winfo_width()
        h = self.container.winfo_height()
        if w <= 50 or h <= 50:
            w = max(600, self.notebook.winfo_width() - 20)
            h = max(400, self.notebook.winfo_height() - 60)
        return w, h

    def focus_vnc(self):
        """Transfer Win32 keyboard focus to the embedded VNC viewer window."""
        if self._is_closing or self._popped_out:
            return
        if self.session and self.session.hwnd and self.session.is_embedded:
            try:
                attached = focus_embedded_window(self.session.hwnd, self.container.winfo_id())
                if attached:
                    self.session.attached_threads = attached
            except Exception:
                pass

    def release_focus(self):
        """Detach Win32 thread input from the embedded VNC window so Tk widgets regain input."""
        if self.session:
            try:
                self.session.detach_thread_input()
            except Exception:
                pass

    def _cancel_scale_timers(self):
        for tid in self._scale_after_ids:
            try:
                self.after_cancel(tid)
            except Exception:
                pass
        self._scale_after_ids.clear()

    def _enforce_scaling(self):
        """Re-verify that the embedded viewer matches this tab's active scaling mode."""
        if self._is_closing or self._popped_out or self._reconnecting:
            return
        if self.session and self.session.hwnd:
            fit = (self.current_scale_mode == "fit")
            self.session.is_scaled = fit
            set_window_scaling(self.session.hwnd, fit=fit)
            w, h = self.get_container_size()
            resize_embedded_window(self.session.hwnd, w, h)
            self._sync_scale_btn()

    def _schedule_scale_enforcement(self):
        self._cancel_scale_timers()
        for delay_ms in (300, 900):
            self._scale_after_ids.append(self.after(delay_ms, self._enforce_scaling))

    def on_window_embedded(self, ready_session: Optional[Session] = None):
        """Called on the UI thread when Win32 window is docked into container."""
        if self._is_closing:
            return
        if ready_session is not None:
            if ready_session._closed:
                return
            self.session = ready_session

        fit = (self.current_scale_mode == "fit")
        self.session.is_scaled = fit
        self.session.is_view_only = self._view_only_active
        self._reconnecting = False

        active_text = "🟢 Sesi Aktif (View-Only)" if self._view_only_active else "🟢 Sesi Aktif"
        active_color = self.colors["warning"] if self._view_only_active else self.colors["online"]
        self.status_lbl.configure(text=active_text, foreground=active_color)

        w, h = self.get_container_size()
        if self.session.hwnd:
            resize_embedded_window(self.session.hwnd, w, h)
            # Ensure TightVNC matches the active scale mode without toggling off an already-active mode
            set_window_scaling(self.session.hwnd, fit=fit)
            self._sync_scale_btn()
            self._sync_view_btn()
            self._schedule_scale_enforcement()
            # Only focus VNC canvas if this session tab is currently selected
            is_current_tab = False
            try:
                is_current_tab = (self.notebook.select() == str(self))
            except Exception:
                pass
            if is_current_tab:
                self.after(50, self.focus_vnc)
            else:
                self.release_focus()

    def _on_container_resize(self, event):
        """Handle resize of container frame."""
        if self.session.hwnd and self.session.is_embedded and event.width > 50 and event.height > 50:
            resize_embedded_window(self.session.hwnd, event.width, event.height)

    def _action_cad(self):
        if self.session.hwnd:
            send_cad_to_window(self.session.hwnd)
            self._show_toast("Sinyal Ctrl+Alt+Del dikirim ke host.")
            self.after(30, self.focus_vnc)
        else:
            self._show_toast("Window belum siap untuk menerima sinyal.")

    def _action_screenshot(self):
        hwnd = self.session.hwnd or self.container.winfo_id()
        ss_dir = self.settings.screenshot_dir or "screenshots"
        os.makedirs(ss_dir, exist_ok=True)
        filename = f"{self.session.host.alias.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.bmp"
        filepath = os.path.join(ss_dir, filename)

        success = capture_window_screenshot(hwnd, filepath)
        if success:
            self._show_toast(f"Screenshot tersimpan: {filename}")
        else:
            self._show_toast("Gagal mengambil screenshot.")
        self.after(30, self.focus_vnc)

    def _action_scale(self):
        """Two-way toggle between Scale: Fit (auto) and Scale: 100% (Original)."""
        self._cancel_scale_timers()
        self.current_scale_mode = "100%" if self.current_scale_mode == "fit" else "fit"
        fit = (self.current_scale_mode == "fit")
        self.session.is_scaled = fit
        self.session.host.scaling = "auto" if fit else "100%"
        self._sync_scale_btn()

        if self.session.hwnd:
            set_window_scaling(self.session.hwnd, fit=fit, force_if_unknown=True)
            w = max(10, self.container.winfo_width())
            h = max(10, self.container.winfo_height())
            resize_embedded_window(self.session.hwnd, w, h)
            self.after(30, self.focus_vnc)

        mode_msg = "Scale: Fit (Auto)" if fit else "Scale: 100% (Original)"
        self._show_toast(f"Tampilan diubah ke {mode_msg}.")

    def _action_toggle_view_only(self):
        """Toggle View-Only live by applying -viewonly directly to the session in-place."""
        self._cancel_scale_timers()
        self._view_only_active = not self._view_only_active
        self.session.host.view_only = self._view_only_active
        fit = (self.current_scale_mode == "fit")
        self.session.is_scaled = fit
        self.session.host.scaling = "auto" if fit else "100%"
        self._sync_view_btn()

        if self.on_in_place_reconnect:
            self._reconnecting = True
            self.status_lbl.configure(
                text=f"🔄 Menerapkan View-Only {'ON' if self._view_only_active else 'OFF'}...",
                foreground=self.colors["accent"]
            )
            self.on_in_place_reconnect(self, self._view_only_active, fit)
        else:
            self._show_toast(f"View-Only: {'Aktif' if self._view_only_active else 'Nonaktif'}")

    def _action_pop_out(self):
        """Detach embedded window back to a standalone Win32 window."""
        if not self.session.hwnd:
            return
        self._popped_out = True
        self._cancel_timers()
        self.session.detach_thread_input()

        # Set parent back to Desktop (NULL / 0)
        user32.SetParent(self.session.hwnd, 0)
        # Restore normal popup style
        old_style = user32.GetWindowLongW(self.session.hwnd, GWL_STYLE)
        new_style = (old_style | WS_POPUP | WS_CAPTION | WS_THICKFRAME) & ~WS_CHILD
        user32.SetWindowLongW(self.session.hwnd, GWL_STYLE, new_style)
        user32.SetWindowPos(self.session.hwnd, 0, 100, 100, 960, 640, SWP_FRAMECHANGED | SWP_SHOWWINDOW)
        self.session.is_embedded = False
        self.status_lbl.configure(text="↗️ Mode Eksternal", foreground=self.colors["text_muted"])
        self.on_close(self, True)

    def _action_reconnect(self):
        h = self.session.host
        self.close_session_tab(confirm=False)
        self.on_reconnect(h)

    def _action_disconnect(self, confirm: bool = True):
        self.close_session_tab(confirm=confirm)

    def close_session_tab(self, confirm: bool = False):
        """Disconnect VNC, terminate viewer process, clean up handles, and close the tab."""
        if self._is_closing or self._popped_out:
            return
        if confirm and self.settings.confirm_disconnect:
            if not messagebox.askyesno("Konfirmasi", f"Putuskan koneksi remote ke '{self.session.host.alias}'?", parent=self):
                return

        self._is_closing = True
        self._cancel_timers()
        self.session.terminate()
        self.on_close(self, False)

    def _on_widget_destroy(self, event):
        if event.widget is self and not self._popped_out and not self._is_closing:
            self._is_closing = True
            self._cancel_timers()
            self.session.terminate()

    def _cancel_timers(self):
        self._cancel_scale_timers()
        for attr in ("_poll_after_id", "_toast_after_id"):
            tid = getattr(self, attr, None)
            if tid:
                try:
                    self.after_cancel(tid)
                except Exception:
                    pass
                setattr(self, attr, None)

    def _show_toast(self, message: str):
        if self._is_closing:
            return
        if self._toast_after_id:
            try:
                self.after_cancel(self._toast_after_id)
            except Exception:
                pass
        self.status_lbl.configure(text=message, foreground=self.colors["accent"])

        def restore_status():
            if self._is_closing:
                return
            active_text = "🟢 Sesi Aktif (View-Only)" if self._view_only_active else "🟢 Sesi Aktif"
            active_color = self.colors["warning"] if self._view_only_active else self.colors["online"]
            self.status_lbl.configure(text=active_text, foreground=active_color)

        self._toast_after_id = self.after(3000, restore_status)

    def _start_poll_alive(self):
        """Periodically check if remote process closed externally."""
        if self._is_closing or self._popped_out:
            return
        if self._reconnecting or self.session.proc is None:
            self._poll_after_id = self.after(1000, self._start_poll_alive)
            return
        if not self.session.is_alive():
            self._is_closing = True
            self._cancel_timers()
            self.status_lbl.configure(text="🔴 Sesi Berakhir", foreground=self.colors["offline"])
            self.on_close(self, False)
            return
        self._poll_after_id = self.after(1000, self._start_poll_alive)
