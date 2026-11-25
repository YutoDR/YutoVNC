"""Settings Dialog for YutoVNC.

Features:
- Scrollable content container ensuring footer action buttons are NEVER cut off.
- Responsive sizing and automatic height clamping for all display resolutions.
- Configuration for VNC viewer executable path, auto-detection, multi-session tabs,
  monitoring interval, screenshot folder, and themes.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
from typing import Optional, Callable
from yutovnc.models import AppSettings
from yutovnc.database import Database
from yutovnc.vnc_launcher import find_viewer_path
from yutovnc.theme import get_theme_colors

class SettingsDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Tk,
        db: Database,
        current_settings: AppSettings,
        on_saved: Optional[Callable[[AppSettings], None]] = None,
        theme_name: str = "dark"
    ):
        super().__init__(parent)
        self.db = db
        self.settings = current_settings
        self.on_saved = on_saved
        self.colors = get_theme_colors(theme_name)

        self.title("⚙️ Pengaturan YutoVNC")
        self.geometry("580x600")
        self.minsize(520, 450)
        self.configure(bg=self.colors["surface"])
        self.transient(parent)
        self.grab_set()

        self._init_ui()
        self._load_data()
        self.center_window()

    def center_window(self):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = 580
        h = min(600, max(450, sh - 90))
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _init_ui(self):
        # 1. Header banner (Pinned at TOP)
        header = ttk.Frame(self, style="Surface.TFrame", padding=(24, 18, 24, 12))
        header.pack(side="top", fill="x")

        ttk.Label(header, text="Pengaturan Aplikasi & Remote Viewer", style="Title.TLabel", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(
            header,
            text="Konfigurasi path executable VNC, mode tab multi-sesi, interval cek, dan tema.",
            style="SurfaceMuted.TLabel"
        ).pack(anchor="w", pady=(2, 0))

        # 2. Footer Bar (Pinned at BOTTOM so action buttons are NEVER cut off)
        footer_container = ttk.Frame(self, style="Surface.TFrame")
        footer_container.pack(side="bottom", fill="x")

        ttk.Separator(footer_container, orient="horizontal").pack(fill="x")

        footer = ttk.Frame(footer_container, style="Surface.TFrame", padding=(24, 12, 24, 16))
        footer.pack(fill="x")

        ttk.Button(footer, text="Batal", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(footer, text="💾 Simpan Pengaturan", style="Primary.TButton", command=self._save_settings).pack(side="right")

        # 3. Middle Scrollable Container
        scroll_outer = ttk.Frame(self, style="Surface.TFrame")
        scroll_outer.pack(side="top", fill="both", expand=True)

        self.canvas = tk.Canvas(
            scroll_outer,
            bg=self.colors["surface"],
            highlightthickness=0,
            borderwidth=0
        )
        self.scrollbar = ttk.Scrollbar(scroll_outer, orient="vertical", command=self.canvas.yview)
        self.form = ttk.Frame(self.canvas, style="Surface.TFrame", padding=(24, 10, 24, 14))

        self.form_win = self.canvas.create_window((0, 0), window=self.form, anchor="nw")

        def _on_form_configure(e):
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))

        def _on_canvas_configure(e):
            self.canvas.itemconfig(self.form_win, width=e.width)

        self.form.bind("<Configure>", _on_form_configure)
        self.canvas.bind("<Configure>", _on_canvas_configure)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # Mousewheel scrolling
        self._bind_mousewheel(self.canvas)
        self._bind_mousewheel(self.form)

        # Build Fields
        self._build_settings_fields(self.form)

    def _bind_mousewheel(self, widget):
        def _on_scroll(event):
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        widget.bind("<MouseWheel>", _on_scroll, add="+")

    def _build_settings_fields(self, form: ttk.Frame):
        form.columnconfigure(0, weight=1)

        # 1. VNC Viewer Path
        ttk.Label(form, text="Path Program VNC Viewer (TightVNC / TigerVNC / UltraVNC) *", style="Surface.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(4, 2))
        
        path_row = ttk.Frame(form, style="Surface.TFrame")
        path_row.pack(fill="x", pady=(0, 4))

        self.path_var = tk.StringVar()
        ttk.Entry(path_row, textvariable=self.path_var).pack(side="left", fill="x", expand=True)
        ttk.Button(path_row, text="Cari...", width=8, command=self._browse_path).pack(side="left", padx=(6, 4))
        ttk.Button(path_row, text="Auto-Detect", width=12, command=self._auto_detect_path).pack(side="left")

        # Path status indicator
        self.path_status_lbl = ttk.Label(form, text="", style="SurfaceMuted.TLabel")
        self.path_status_lbl.pack(anchor="w", pady=(0, 12))

        # 2. Connection Mode (Embedded Tab vs External Window)
        ttk.Label(form, text="Mode Tampilan Sesi Remote:", style="Surface.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(4, 2))
        self.embed_var = tk.BooleanVar(value=True)
        mode_frame = ttk.Frame(form, style="Surface.TFrame")
        mode_frame.pack(fill="x", pady=(0, 12))

        ttk.Radiobutton(
            mode_frame,
            text="Multi-Session Tab (Embedded dalam jendela YutoVNC) - Disarankan",
            variable=self.embed_var,
            value=True,
            style="Surface.TRadiobutton"
        ).pack(anchor="w", pady=(2, 4))

        ttk.Radiobutton(
            mode_frame,
            text="Jendela Eksternal Terpisah (Buka tvnviewer.exe biasa)",
            variable=self.embed_var,
            value=False,
            style="Surface.TRadiobutton"
        ).pack(anchor="w")

        # 3. Status monitor refresh interval
        ttk.Label(form, text="Interval Auto-Check Status Online/Offline:", style="Surface.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(4, 2))
        self.interval_var = tk.StringVar(value="15")
        interval_combo = ttk.Combobox(
            form,
            textvariable=self.interval_var,
            values=["0 (Nonaktif)", "10 detik", "15 detik", "30 detik", "60 detik"],
            state="readonly"
        )
        interval_combo.pack(fill="x", pady=(0, 12))

        # 4. Screenshot directory
        ttk.Label(form, text="Folder Penyimpanan Screenshot:", style="Surface.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(4, 2))
        ss_row = ttk.Frame(form, style="Surface.TFrame")
        ss_row.pack(fill="x", pady=(0, 12))

        self.ss_dir_var = tk.StringVar(value="screenshots")
        ttk.Entry(ss_row, textvariable=self.ss_dir_var).pack(side="left", fill="x", expand=True)
        ttk.Button(ss_row, text="Pilih...", width=8, command=self._browse_ss_dir).pack(side="left", padx=(6, 0))

        # 5. Theme
        ttk.Label(form, text="Tema Tampilan:", style="Surface.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(4, 2))
        self.theme_var = tk.StringVar(value="dark")
        theme_combo = ttk.Combobox(
            form,
            textvariable=self.theme_var,
            values=["dark", "light"],
            state="readonly"
        )
        theme_combo.pack(fill="x", pady=(0, 12))

    def _browse_path(self):
        filename = filedialog.askopenfilename(
            title="Pilih Executable VNC Viewer",
            filetypes=[("Executable Files", "*.exe"), ("All Files", "*.*")],
            parent=self
        )
        if filename:
            self.path_var.set(filename)
            self._check_path_validity()

    def _auto_detect_path(self):
        detected = find_viewer_path()
        self.path_var.set(detected)
        self._check_path_validity()

    def _check_path_validity(self):
        p = self.path_var.get().strip()
        if os.path.exists(p):
            self.path_status_lbl.configure(text=f"✓ Ditemukan: {p}", foreground=self.colors["online"])
        else:
            self.path_status_lbl.configure(text="✗ File tidak ditemukan di lokasi ini", foreground=self.colors["offline"])

    def _browse_ss_dir(self):
        d = filedialog.askdirectory(title="Pilih Folder Screenshot", parent=self)
        if d:
            self.ss_dir_var.set(d)

    def _load_data(self):
        self.path_var.set(self.settings.vnc_viewer_path)
        self.embed_var.set(self.settings.embed_in_tab)
        iv = self.settings.auto_refresh_interval
        if iv == 0:
            self.interval_var.set("0 (Nonaktif)")
        else:
            self.interval_var.set(f"{iv} detik")
        self.ss_dir_var.set(self.settings.screenshot_dir)
        self.theme_var.set(self.settings.theme)
        self._check_path_validity()

    def _save_settings(self):
        path = self.path_var.get().strip()
        if not path:
            messagebox.showwarning("Perhatian", "Path VNC Viewer tidak boleh kosong.", parent=self)
            return

        self.settings.vnc_viewer_path = path
        self.settings.embed_in_tab = self.embed_var.get()

        # Parse interval
        iv_text = self.interval_var.get()
        if "0" in iv_text:
            self.settings.auto_refresh_interval = 0
        elif "10" in iv_text:
            self.settings.auto_refresh_interval = 10
        elif "15" in iv_text:
            self.settings.auto_refresh_interval = 15
        elif "30" in iv_text:
            self.settings.auto_refresh_interval = 30
        elif "60" in iv_text:
            self.settings.auto_refresh_interval = 60
        else:
            self.settings.auto_refresh_interval = 15

        self.settings.screenshot_dir = self.ss_dir_var.get().strip() or "screenshots"
        self.settings.theme = self.theme_var.get()

        self.db.save_all_settings(self.settings)

        if self.on_saved:
            self.on_saved(self.settings)

        messagebox.showinfo("Berhasil", "Pengaturan berhasil disimpan.", parent=self)
        self.destroy()
