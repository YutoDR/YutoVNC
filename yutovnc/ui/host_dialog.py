"""Host Add/Edit Dialog for YutoVNC.

Features:
- Scrollable content container ensuring footer action buttons are NEVER cut off.
- Responsive sizing and automatic height clamping for all display resolutions.
- Automatic default VNC port (5900) with dedicated "Custom Port" toggle checkbox.
- Live port reachability testing (Port 5900 / Custom Port probe).
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
from typing import Optional, Callable
from yutovnc.models import Host
from yutovnc.database import Database
from yutovnc.security import encrypt_password_dpapi, decrypt_password_dpapi
from yutovnc.monitor import StatusMonitor
from yutovnc.theme import get_theme_colors

class HostDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Tk,
        db: Database,
        monitor: StatusMonitor,
        host: Optional[Host] = None,
        on_saved: Optional[Callable[[Host], None]] = None,
        theme_name: str = "dark"
    ):
        super().__init__(parent)
        self.db = db
        self.monitor = monitor
        self.host = host
        self.on_saved = on_saved
        self.colors = get_theme_colors(theme_name)

        self.title("✏️ Edit Host" if (host and host.id is not None) else "➕ Tambah Host Baru")
        self.geometry("560x680")
        self.minsize(500, 480)
        self.configure(bg=self.colors["surface"])
        self.transient(parent)
        self.grab_set()

        self._show_password = False
        self._init_ui()
        self._load_data()
        self.center_window()

    def center_window(self):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = 560
        # Automatically clamp height so dialog fits within screen on small displays
        h = min(680, max(480, sh - 90))
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _init_ui(self):
        # 1. Header banner (Pinned at TOP)
        header = ttk.Frame(self, style="Surface.TFrame", padding=(24, 18, 24, 12))
        header.pack(side="top", fill="x")

        title_text = "Edit Profil Host Remote" if (self.host and self.host.id is not None) else "Daftarkan Komputer / Host Baru"
        ttk.Label(header, text=title_text, style="Title.TLabel", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(
            header,
            text="Kelola nama alias, alamat IP, grup, dan password VNC yang terenkripsi.",
            style="SurfaceMuted.TLabel"
        ).pack(anchor="w", pady=(2, 0))

        # 2. Footer Bar (Pinned at BOTTOM so action buttons are NEVER cut off)
        footer_container = ttk.Frame(self, style="Surface.TFrame")
        footer_container.pack(side="bottom", fill="x")

        ttk.Separator(footer_container, orient="horizontal").pack(fill="x")

        footer = ttk.Frame(footer_container, style="Surface.TFrame", padding=(24, 12, 24, 16))
        footer.pack(fill="x")

        ttk.Button(footer, text="Batal", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(footer, text="💾 Simpan Host", style="Primary.TButton", command=self._save_host).pack(side="right")

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

        # Bind mouse wheel scrolling
        self._bind_mousewheel(self.canvas)
        self._bind_mousewheel(self.form)

        # Build Form Controls inside self.form
        self._build_form_fields(self.form)

    def _bind_mousewheel(self, widget):
        def _on_scroll(event):
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        widget.bind("<MouseWheel>", _on_scroll, add="+")

    def _build_form_fields(self, form: ttk.Frame):
        form.columnconfigure(0, weight=1)

        # 1. Alias Name
        ttk.Label(form, text="Nama Alias / Ruangan *", style="Surface.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(4, 2))
        self.alias_var = tk.StringVar()
        self.alias_entry = ttk.Entry(form, textvariable=self.alias_var)
        self.alias_entry.pack(fill="x", pady=(0, 10))
        self.alias_entry.focus()

        # 2. IP Address & Port Section
        ip_section = ttk.Frame(form, style="Surface.TFrame")
        ip_section.pack(fill="x", pady=(0, 10))
        ip_section.columnconfigure(0, weight=3)
        ip_section.columnconfigure(1, weight=2)

        # Left Column: IP Address
        ip_col = ttk.Frame(ip_section, style="Surface.TFrame")
        ip_col.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ttk.Label(ip_col, text="IP Address / Hostname *", style="Surface.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 2))
        self.ip_var = tk.StringVar()
        self.ip_entry = ttk.Entry(ip_col, textvariable=self.ip_var)
        self.ip_entry.pack(fill="x")

        # Right Column: Port & Custom Port Checkbox
        port_col = ttk.Frame(ip_section, style="Surface.TFrame")
        port_col.grid(row=0, column=1, sticky="nsew")

        port_hdr = ttk.Frame(port_col, style="Surface.TFrame")
        port_hdr.pack(fill="x", pady=(0, 2))
        ttk.Label(port_hdr, text="Port VNC", style="Surface.TLabel", font=("Segoe UI", 9, "bold")).pack(side="left")

        # Custom Port Checkbox
        self.custom_port_var = tk.BooleanVar(value=False)
        self.custom_port_chk = ttk.Checkbutton(
            port_hdr,
            text="Custom Port",
            variable=self.custom_port_var,
            command=self._on_custom_port_toggle,
            style="Surface.TCheckbutton"
        )
        self.custom_port_chk.pack(side="right")

        port_input_row = ttk.Frame(port_col, style="Surface.TFrame")
        port_input_row.pack(fill="x")

        self.port_var = tk.StringVar(value="5900")
        self.port_entry = ttk.Entry(port_input_row, textvariable=self.port_var, state="disabled")
        self.port_entry.pack(side="left", fill="x", expand=True)

        self.port_hint_lbl = ttk.Label(
            port_col,
            text="Port default 5900 aktif",
            style="SurfaceMuted.TLabel",
            font=("Segoe UI", 8)
        )
        self.port_hint_lbl.pack(anchor="w", pady=(2, 0))

        # 3. Group / Category
        ttk.Label(form, text="Grup / Kategori", style="Surface.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(4, 2))
        self.group_var = tk.StringVar(value="Default")
        existing_groups = self.db.get_groups()
        self.group_combo = ttk.Combobox(form, textvariable=self.group_var, values=existing_groups)
        self.group_combo.pack(fill="x", pady=(0, 10))

        # 4. Password VNC
        ttk.Label(form, text="Password VNC (Terenkripsi Windows DPAPI)", style="Surface.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(4, 2))
        pw_frame = ttk.Frame(form, style="Surface.TFrame")
        pw_frame.pack(fill="x", pady=(0, 10))

        self.pw_var = tk.StringVar()
        self.pw_entry = ttk.Entry(pw_frame, textvariable=self.pw_var, show="*")
        self.pw_entry.pack(side="left", fill="x", expand=True)

        self.toggle_pw_btn = ttk.Button(pw_frame, text="👁️ Lihat", width=8, command=self._toggle_password)
        self.toggle_pw_btn.pack(side="right", padx=(8, 0))

        # 5. Display options (View-Only, Fullscreen, Favorite)
        ttk.Label(form, text="Opsi Tampilan & Favorit", style="Surface.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(4, 2))
        opts_frame = ttk.Frame(form, style="Surface.TFrame")
        opts_frame.pack(fill="x", pady=(0, 10))

        self.view_only_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts_frame, text="Mode Hanya Lihat (View-Only)", variable=self.view_only_var, style="Surface.TCheckbutton").pack(side="left", padx=(0, 16))

        self.fullscreen_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts_frame, text="Layar Penuh", variable=self.fullscreen_var, style="Surface.TCheckbutton").pack(side="left", padx=(0, 16))

        self.favorite_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts_frame, text="Favorit ⭐", variable=self.favorite_var, style="Surface.TCheckbutton").pack(side="left")

        # 6. Scaling
        ttk.Label(form, text="Skala Layar Remote:", style="Surface.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(4, 2))
        self.scaling_var = tk.StringVar(value="auto")
        scale_combo = ttk.Combobox(form, textvariable=self.scaling_var, values=["auto", "fit", "100%", "none"], state="readonly")
        scale_combo.pack(fill="x", pady=(0, 10))

        # 7. Notes
        ttk.Label(form, text="Catatan / Keterangan (Opsional)", style="Surface.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(4, 2))
        self.notes_text = tk.Text(
            form,
            height=3,
            bg=self.colors["entry_bg"],
            fg=self.colors["entry_fg"],
            insertbackground=self.colors["text"],
            relief="flat",
            font=("Segoe UI", 9)
        )
        self.notes_text.pack(fill="x", pady=(0, 12))

        # 8. Test Connection Bar
        test_bar = ttk.Frame(form, style="Surface.TFrame")
        test_bar.pack(fill="x", pady=(2, 6))

        self.test_btn = ttk.Button(test_bar, text="🔍 Tes Port VNC", command=self._test_connection)
        self.test_btn.pack(side="left")

        self.test_status_lbl = ttk.Label(test_bar, text="", style="SurfaceMuted.TLabel")
        self.test_status_lbl.pack(side="left", padx=(10, 0))

    def _on_custom_port_toggle(self):
        """Enable or disable port input based on checkbox."""
        if self.custom_port_var.get():
            self.port_entry.configure(state="normal")
            self.port_entry.focus()
            self.port_entry.selection_range(0, "end")
            self.port_hint_lbl.configure(text="Masukkan nomor port kustom (1-65535)")
        else:
            self.port_var.set("5900")
            self.port_entry.configure(state="disabled")
            self.port_hint_lbl.configure(text="Port default 5900 aktif")

    def _toggle_password(self):
        self._show_password = not self._show_password
        if self._show_password:
            self.pw_entry.configure(show="")
            self.toggle_pw_btn.configure(text="🔒 Sembunyi")
        else:
            self.pw_entry.configure(show="*")
            self.toggle_pw_btn.configure(text="👁️ Lihat")

    def _load_data(self):
        if not self.host:
            # New host: Default port 5900, custom port unchecked
            self.custom_port_var.set(False)
            self.port_var.set("5900")
            self.port_entry.configure(state="disabled")
            return

        self.alias_var.set(self.host.alias)
        self.ip_var.set(self.host.ip)

        # Port loading: if port is custom (!= 5900), enable custom port checkbox
        h_port = self.host.port or 5900
        if h_port != 5900:
            self.custom_port_var.set(True)
            self.port_var.set(str(h_port))
            self.port_entry.configure(state="normal")
            self.port_hint_lbl.configure(text="Port kustom aktif")
        else:
            self.custom_port_var.set(False)
            self.port_var.set("5900")
            self.port_entry.configure(state="disabled")
            self.port_hint_lbl.configure(text="Port default 5900 aktif")

        self.group_var.set(self.host.group)
        self.view_only_var.set(self.host.view_only)
        self.fullscreen_var.set(self.host.fullscreen)
        self.scaling_var.set(self.host.scaling)
        self.favorite_var.set(self.host.is_favorite)
        if self.host.notes:
            self.notes_text.insert("1.0", self.host.notes)

        # Decrypt password for editing
        if self.host.password_enc:
            try:
                plain = decrypt_password_dpapi(self.host.password_enc)
                self.pw_var.set(plain)
            except Exception:
                self.pw_var.set("")

    def _test_connection(self):
        ip = self.ip_var.get().strip()
        if not ip:
            messagebox.showwarning("Perhatian", "Masukkan alamat IP terlebih dahulu.", parent=self)
            return

        # Determine port to test
        if self.custom_port_var.get():
            try:
                port = int(self.port_var.get().strip())
                if not (1 <= port <= 65535):
                    raise ValueError()
            except ValueError:
                messagebox.showwarning("Validasi", "Nomor Port kustom tidak valid (1 - 65535).", parent=self)
                return
        else:
            port = 5900

        self.test_btn.configure(state="disabled")
        self.test_status_lbl.configure(text=f"Memeriksa port {port}...", foreground=self.colors["text_muted"])

        temp_host = Host(alias="Test", ip=ip, port=port)

        def worker():
            status = self.monitor.check_host_sync(temp_host, timeout=2.0)
            def update_ui():
                self.test_btn.configure(state="normal")
                if status.online:
                    self.test_status_lbl.configure(
                        text=f"🟢 Online (Port {port} terbuka, {status.latency_ms} ms)",
                        foreground=self.colors["online"]
                    )
                else:
                    self.test_status_lbl.configure(
                        text=f"🔴 Offline (Port {port}): {status.error_message}",
                        foreground=self.colors["offline"]
                    )
            self.after(0, update_ui)

        threading.Thread(target=worker, daemon=True).start()

    def _save_host(self):
        alias = self.alias_var.get().strip()
        ip = self.ip_var.get().strip()
        group = self.group_var.get().strip() or "Default"
        plain_pw = self.pw_var.get()
        notes = self.notes_text.get("1.0", "end-1c").strip()

        if not alias:
            messagebox.showwarning("Validasi", "Nama Alias / Ruangan wajib diisi.", parent=self)
            self.alias_entry.focus()
            return
        if not ip:
            messagebox.showwarning("Validasi", "Alamat IP wajib diisi.", parent=self)
            self.ip_entry.focus()
            return

        # Determine and validate port
        if self.custom_port_var.get():
            port_s = self.port_var.get().strip()
            try:
                port = int(port_s)
                if not (1 <= port <= 65535):
                    raise ValueError()
            except ValueError:
                messagebox.showwarning("Validasi", "Nomor Port kustom tidak valid (1 - 65535).", parent=self)
                self.port_entry.focus()
                return
        else:
            port = 5900

        # Encrypt password using DPAPI
        enc_pw = ""
        if plain_pw:
            try:
                enc_pw = encrypt_password_dpapi(plain_pw)
            except Exception as e:
                messagebox.showerror("Enkripsi Gagal", f"Gagal mengenkripsi password dengan Windows DPAPI: {e}", parent=self)
                return

        # Ensure group exists
        self.db.add_group(group)

        if self.host and self.host.id is not None:
            # Update existing
            self.host.alias = alias
            self.host.ip = ip
            self.host.port = port
            self.host.group = group
            self.host.password_enc = enc_pw
            self.host.view_only = self.view_only_var.get()
            self.host.fullscreen = self.fullscreen_var.get()
            self.host.scaling = self.scaling_var.get()
            self.host.notes = notes
            self.host.is_favorite = self.favorite_var.get()
            self.db.update_host(self.host)
            saved_host = self.host
        else:
            # Create new
            new_host = Host(
                alias=alias,
                ip=ip,
                port=port,
                group=group,
                password_enc=enc_pw,
                view_only=self.view_only_var.get(),
                fullscreen=self.fullscreen_var.get(),
                scaling=self.scaling_var.get(),
                notes=notes,
                is_favorite=self.favorite_var.get()
            )
            h_id = self.db.add_host(new_host)
            new_host.id = h_id
            saved_host = new_host

        if self.on_saved:
            self.on_saved(saved_host)

        self.destroy()
