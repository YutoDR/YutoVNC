"""Network & VNC Scanner Dialog for YutoVNC.

Allows users to scan their local network subnet to automatically discover
PCs with active VNC servers (Port 5900 / custom port) and add them to the Host Address Book.
Includes checkbox multi-selection and sets default group to 'Default'.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable, List, Set
import threading

from yutovnc.database import Database
from yutovnc.models import Host
from yutovnc.monitor import StatusMonitor
from yutovnc.scanner import NetworkScanner, ScanResult
from yutovnc.theme import get_theme_colors
from yutovnc.ui.host_dialog import HostDialog

class ScannerDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Tk,
        db: Database,
        monitor: Optional[StatusMonitor] = None,
        on_hosts_added: Optional[Callable[[], None]] = None,
        theme_name: str = "dark"
    ):
        super().__init__(parent)
        self.db = db
        self.monitor = monitor or StatusMonitor()
        self.on_hosts_added = on_hosts_added
        self.colors = get_theme_colors(theme_name)
        self.scanner = NetworkScanner(max_workers=64)

        self.title("📡 Pemindai Jaringan (VNC Network Scanner)")
        self.geometry("880x660")
        self.minsize(780, 520)
        self.configure(bg=self.colors["surface"])
        self.transient(parent)
        self.grab_set()

        # Cache of scan results, checked row keys, and database existing IP:port set
        self.results: List[ScanResult] = []
        self.checked_keys: Set[str] = set()
        self.existing_hosts_set = self._get_existing_hosts_set()

        self._init_ui()
        self.center_window()

        # Handle window close while scanning
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

    def center_window(self):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = 880
        h = min(660, max(520, sh - 90))
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _get_existing_hosts_set(self) -> set:
        hosts = self.db.get_all_hosts()
        return {(h.ip.strip(), h.port) for h in hosts}

    def _init_ui(self):
        # 1. Pinned Header Banner
        header = ttk.Frame(self, style="Surface.TFrame", padding=(20, 14, 20, 8))
        header.pack(side="top", fill="x")

        ttk.Label(header, text="📡 Pemindai Jaringan Lokal (VNC Scanner)", style="Title.TLabel", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(
            header,
            text="Deteksi otomatis seluruh komputer di subnet lokal yang mengaktifkan VNC dan pilih untuk ditambahkan ke grup Default.",
            style="SurfaceMuted.TLabel"
        ).pack(anchor="w", pady=(2, 0))

        # 2. Pinned Footer Bar
        footer_container = ttk.Frame(self, style="Surface.TFrame")
        footer_container.pack(side="bottom", fill="x")

        ttk.Separator(footer_container, orient="horizontal").pack(fill="x")

        footer = ttk.Frame(footer_container, style="Surface.TFrame", padding=(20, 10, 20, 12))
        footer.pack(fill="x")

        self.footer_stats_lbl = ttk.Label(footer, text="Siap memindai subnet lokal.", style="SurfaceMuted.TLabel")
        self.footer_stats_lbl.pack(side="left")

        ttk.Button(footer, text="Tutup", command=self._on_closing).pack(side="right", padx=(8, 0))
        self.add_selected_btn = ttk.Button(
            footer,
            text="➕ Tambah Terpilih (0)",
            style="Primary.TButton",
            command=self._add_checked_to_hosts
        )
        self.add_selected_btn.pack(side="right", padx=(4, 0))

        self.batch_add_btn = ttk.Button(
            footer,
            text="⚡ Tambah Semua VNC Aktif",
            style="Success.TButton",
            command=self._batch_add_all_active
        )
        self.batch_add_btn.pack(side="right", padx=(4, 4))

        # 3. Main Center Content
        main_content = ttk.Frame(self, style="Surface.TFrame", padding=(20, 8, 20, 4))
        main_content.pack(side="top", fill="both", expand=True)

        # Config Panel (Subnet, Port, Start/Stop)
        cfg_panel = ttk.Frame(main_content, style="Surface.TFrame")
        cfg_panel.pack(fill="x", pady=(0, 10))

        # Target Subnet input
        ttk.Label(cfg_panel, text="Subnet / Rentang IP:", style="Surface.TLabel", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 6))

        def_cidr, def_s, def_e = NetworkScanner.get_default_subnet()
        self.target_var = tk.StringVar(value=def_cidr)
        self.target_entry = ttk.Entry(cfg_panel, textvariable=self.target_var, width=24)
        self.target_entry.grid(row=0, column=1, sticky="w", padx=(0, 16))

        # Port input
        ttk.Label(cfg_panel, text="Port VNC:", style="Surface.TLabel", font=("Segoe UI", 9, "bold")).grid(row=0, column=2, sticky="w", padx=(0, 6))
        self.port_var = tk.StringVar(value="5900")
        self.port_entry = ttk.Entry(cfg_panel, textvariable=self.port_var, width=8)
        self.port_entry.grid(row=0, column=3, sticky="w", padx=(0, 16))

        # Scan & Stop Action Buttons
        self.scan_btn = ttk.Button(cfg_panel, text="▶ Mulai Scan", style="Primary.TButton", command=self._start_scan)
        self.scan_btn.grid(row=0, column=4, padx=(0, 6))

        self.stop_btn = ttk.Button(cfg_panel, text="⏹ Stop", style="Danger.TButton", command=self._stop_scan, state="disabled")
        self.stop_btn.grid(row=0, column=5)

        # Progress bar & scan status text
        prog_frame = ttk.Frame(main_content, style="Surface.TFrame")
        prog_frame.pack(fill="x", pady=(0, 8))

        self.progress_bar = ttk.Progressbar(prog_frame, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill="x", pady=(0, 4))

        self.status_lbl = ttk.Label(
            prog_frame,
            text=f"Target terdeteksi: {def_cidr} ({def_s} s/d {def_e})",
            style="SurfaceMuted.TLabel"
        )
        self.status_lbl.pack(anchor="w")

        # Filter and Checkbox Selection Subbar
        filter_bar = ttk.Frame(main_content, style="Surface.TFrame")
        filter_bar.pack(fill="x", pady=(4, 6))

        self.active_only_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            filter_bar,
            text="Hanya tampilkan VNC Aktif 🟢",
            variable=self.active_only_var,
            command=self._refresh_results_table,
            style="Surface.TCheckbutton"
        ).pack(side="left")

        # Selection convenience buttons
        ttk.Button(filter_bar, text="☑ Pilih Semua", command=self._select_all_visible).pack(side="left", padx=(14, 4))
        ttk.Button(filter_bar, text="☐ Batal Semua", command=self._deselect_all).pack(side="left", padx=(0, 4))

        # Quick text search filter in results
        search_sub = ttk.Frame(filter_bar, style="Surface.TFrame")
        search_sub.pack(side="right")
        ttk.Label(search_sub, text="🔍", style="SurfaceMuted.TLabel").pack(side="left", padx=(0, 4))
        self.search_filter_var = tk.StringVar()
        self.search_filter_var.trace_add("write", lambda *_: self._refresh_results_table())
        ttk.Entry(search_sub, textvariable=self.search_filter_var, width=18).pack(side="left")

        # Results Table (Treeview)
        table_container = ttk.Frame(main_content, style="Surface.TFrame")
        table_container.pack(fill="both", expand=True)

        cols = ("check", "status", "ip", "hostname", "port", "latency", "db_status")
        self.tree = ttk.Treeview(table_container, columns=cols, show="headings", selectmode="extended")

        self.tree.heading("check", text="Pilih", command=self._toggle_select_all)
        self.tree.heading("status", text="Status VNC")
        self.tree.heading("ip", text="IP Address")
        self.tree.heading("hostname", text="Nama Komputer (Hostname)")
        self.tree.heading("port", text="Port")
        self.tree.heading("latency", text="Latensi")
        self.tree.heading("db_status", text="Status Database")

        self.tree.column("check", width=55, anchor="center")
        self.tree.column("status", width=120, anchor="w")
        self.tree.column("ip", width=135, anchor="w")
        self.tree.column("hostname", width=210, anchor="w")
        self.tree.column("port", width=65, anchor="center")
        self.tree.column("latency", width=80, anchor="center")
        self.tree.column("db_status", width=120, anchor="center")

        tree_scroll = ttk.Scrollbar(table_container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)

        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")

        # Bind events: click column for check, spacebar for toggle, double-click for edit/add
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<space>", self._on_tree_space)
        self.tree.bind("<Double-1>", self._on_tree_double_click)

    def _start_scan(self):
        target = self.target_var.get().strip()
        port_s = self.port_var.get().strip()

        if not target:
            messagebox.showwarning("Perhatian", "Masukkan target subnet atau rentang IP.", parent=self)
            return

        try:
            port = int(port_s)
            if not (1 <= port <= 65535):
                raise ValueError()
        except ValueError:
            messagebox.showwarning("Validasi", "Nomor Port tidak valid (1 - 65535).", parent=self)
            return

        ips = NetworkScanner.parse_target_ips(target)
        if not ips:
            messagebox.showwarning("Format Salah", "Format subnet / IP tidak valid. Contoh: 192.168.1.0/24 atau 192.168.1.1 - 192.168.1.50", parent=self)
            return

        # Reset state & table
        self.results.clear()
        self.checked_keys.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)

        total_ips = len(ips)
        self.progress_bar.configure(maximum=total_ips, value=0)
        self.scan_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.status_lbl.configure(text=f"Memindai {total_ips} IP pada port {port}...", foreground=self.colors["accent"])
        self._update_action_counts()

        active_count = 0

        def on_result(res: ScanResult):
            nonlocal active_count
            if res.is_open:
                active_count += 1
                # Automatically pre-check newly discovered active VNC servers
                if (res.ip, res.port) not in self.existing_hosts_set:
                    self.checked_keys.add(f"{res.ip}:{res.port}")

            self.results.append(res)
            self._insert_single_result(res)
            self._update_action_counts()

        def on_progress(scanned: int, total: int):
            def update_ui():
                pct = int((scanned / total) * 100) if total > 0 else 0
                self.progress_bar.configure(value=scanned)
                self.status_lbl.configure(
                    text=f"Memindai: {scanned} / {total} IP ({pct}%) | 🟢 Ditemukan: {active_count} VNC Aktif",
                    foreground=self.colors["accent"]
                )
            self.after(0, update_ui)

        def on_complete(all_res: List[ScanResult]):
            def finish_ui():
                self.scan_btn.configure(state="normal")
                self.stop_btn.configure(state="disabled")
                total_open = sum(1 for r in self.results if r.is_open)
                self.status_lbl.configure(
                    text=f"✓ Pemindaian selesai! Ditemukan {total_open} PC dengan VNC aktif dari {len(self.results)} IP.",
                    foreground=self.colors["online"] if total_open > 0 else self.colors["text_muted"]
                )
                self._refresh_results_table()
                self._update_action_counts()
            self.after(0, finish_ui)

        # Launch background scan
        self.scanner.scan_network_async(
            ips=ips,
            port=port,
            timeout=0.4,
            on_result=lambda r: self.after(0, lambda: on_result(r)),
            on_progress=on_progress,
            on_complete=on_complete
        )

    def _stop_scan(self):
        self.scanner.stop()
        self.stop_btn.configure(state="disabled")
        self.scan_btn.configure(state="normal")
        self.status_lbl.configure(text="Pemindaian dihentikan oleh pengguna.", foreground=self.colors["warning"])
        self._update_action_counts()

    def _insert_single_result(self, res: ScanResult):
        # Check active only filter
        if self.active_only_var.get() and not res.is_open:
            return

        # Check search query
        q = self.search_filter_var.get().strip().lower()
        if q and (q not in res.ip.lower() and q not in res.hostname.lower()):
            return

        row_key = f"{res.ip}:{res.port}"
        is_checked = row_key in self.checked_keys
        check_sym = "☑" if is_checked else "☐"

        status_text = "🟢 VNC Aktif" if res.is_open else "🔴 Tertutup"
        latency_text = f"{res.latency_ms} ms" if res.is_open else "-"
        host_name = res.hostname or "-"

        is_saved = (res.ip, res.port) in self.existing_hosts_set
        db_text = "✓ Sudah Ada" if is_saved else "➕ Tambah"

        self.tree.insert(
            "",
            "end",
            iid=row_key,
            values=(check_sym, status_text, res.ip, host_name, res.port, latency_text, db_text)
        )

    def _refresh_results_table(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        for res in self.results:
            self._insert_single_result(res)

    def _update_row_check_state(self, row_id: str):
        if self.tree.exists(row_id):
            vals = list(self.tree.item(row_id, "values"))
            if vals:
                vals[0] = "☑" if row_id in self.checked_keys else "☐"
                self.tree.item(row_id, values=vals)

    def _toggle_check(self, row_id: str):
        if row_id in self.checked_keys:
            self.checked_keys.remove(row_id)
        else:
            self.checked_keys.add(row_id)
        self._update_row_check_state(row_id)
        self._update_action_counts()

    def _select_all_visible(self):
        """Check all currently visible rows that are not yet saved."""
        for item in self.tree.get_children():
            self.checked_keys.add(item)
            self._update_row_check_state(item)
        self._update_action_counts()

    def _deselect_all(self):
        """Uncheck all rows."""
        self.checked_keys.clear()
        for item in self.tree.get_children():
            self._update_row_check_state(item)
        self._update_action_counts()

    def _toggle_select_all(self):
        children = self.tree.get_children()
        if not children:
            return
        all_checked = all(c in self.checked_keys for c in children)
        if all_checked:
            self._deselect_all()
        else:
            self._select_all_visible()

    def _update_action_counts(self):
        # Count checked items that are not yet in database
        checked_unadded = [
            k for k in self.checked_keys
            if not any(f"{r.ip}:{r.port}" == k and (r.ip, r.port) in self.existing_hosts_set for r in self.results)
        ]
        count = len(checked_unadded)
        self.add_selected_btn.configure(text=f"➕ Tambah Terpilih ({count})")
        total_open = sum(1 for r in self.results if r.is_open)
        self.footer_stats_lbl.configure(
            text=f"Total: {len(self.results)} IP | 🟢 {total_open} VNC Aktif | ☑ {len(self.checked_keys)} Dicentang"
        )

    def _on_tree_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        col = self.tree.identify_column(event.x)
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return

        # Clicked Checkbox column (#1)
        if col == "#1":
            self._toggle_check(row_id)
            return "break"

        # Clicked Status Database column (#7)
        if col == "#7":
            # If not yet saved in DB, open HostDialog
            is_saved = any(f"{r.ip}:{r.port}" == row_id and (r.ip, r.port) in self.existing_hosts_set for r in self.results)
            if not is_saved:
                self._open_host_dialog_for_row(row_id)
                return "break"

    def _on_tree_space(self, event):
        selected = self.tree.selection()
        if not selected:
            return
        all_checked = all(s in self.checked_keys for s in selected)
        for s in selected:
            if all_checked:
                self.checked_keys.discard(s)
            else:
                self.checked_keys.add(s)
            self._update_row_check_state(s)
        self._update_action_counts()
        return "break"

    def _on_tree_double_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        col = self.tree.identify_column(event.x)
        if col == "#1":
            return  # Handled by click toggle
        row_id = self.tree.identify_row(event.y)
        if row_id:
            self._open_host_dialog_for_row(row_id)

    def _open_host_dialog_for_row(self, row_id: str):
        matching = [r for r in self.results if f"{r.ip}:{r.port}" == row_id]
        if not matching:
            return
        res = matching[0]

        alias_name = res.hostname if res.hostname else f"PC {res.ip}"
        temp_host = Host(
            alias=alias_name,
            ip=res.ip,
            port=res.port,
            group="Default",
            notes="Ditemukan via Pemindai Jaringan"
        )

        def on_saved(saved: Host):
            self.existing_hosts_set.add((saved.ip.strip(), saved.port))
            self.checked_keys.discard(f"{saved.ip.strip()}:{saved.port}")
            self._refresh_results_table()
            self._update_action_counts()
            if self.on_hosts_added:
                self.on_hosts_added()

        HostDialog(
            self,
            self.db,
            monitor=self.monitor,
            host=temp_host,
            on_saved=on_saved,
            theme_name=self.colors["name"]
        )

    def _add_checked_to_hosts(self):
        """Add all checked scan results to the database with group='Default'."""
        checked_unadded = [
            r for r in self.results
            if f"{r.ip}:{r.port}" in self.checked_keys and (r.ip, r.port) not in self.existing_hosts_set
        ]

        if not checked_unadded:
            if not self.checked_keys:
                messagebox.showinfo("Pilih PC", "Belum ada PC yang dicentang.\nSilakan centang kotak ☑ pada baris PC yang ingin ditambahkan.", parent=self)
            else:
                messagebox.showinfo("Informasi", "Seluruh PC yang dicentang sudah terdaftar di database.", parent=self)
            return

        # Ensure Default group exists
        self.db.add_group("Default")
        added_count = 0
        for r in checked_unadded:
            alias = r.hostname if r.hostname else f"PC {r.ip}"
            new_h = Host(
                alias=alias,
                ip=r.ip,
                port=r.port,
                group="Default",
                notes="Ditemukan via Pemindai Jaringan"
            )
            self.db.add_host(new_h)
            self.existing_hosts_set.add((r.ip, r.port))
            self.checked_keys.discard(f"{r.ip}:{r.port}")
            added_count += 1

        self._refresh_results_table()
        self._update_action_counts()

        if self.on_hosts_added:
            self.on_hosts_added()

        messagebox.showinfo("Berhasil", f"Berhasil menambahkan {added_count} host ke dalam grup 'Default'.", parent=self)

    def _batch_add_all_active(self):
        """Quickly add all discovered open VNC servers that are not yet in database into group 'Default'."""
        active_unadded = [
            r for r in self.results
            if r.is_open and (r.ip, r.port) not in self.existing_hosts_set
        ]

        if not active_unadded:
            messagebox.showinfo("Informasi", "Tidak ada VNC aktif baru yang belum terdaftar.", parent=self)
            return

        msg = f"Ditemukan {len(active_unadded)} PC dengan VNC aktif yang belum ada di database.\n\nTambahkan seluruh PC ini ke grup 'Default' sekarang?"
        if not messagebox.askyesno("Tambah Cepat", msg, parent=self):
            return

        self.db.add_group("Default")
        added_count = 0
        for r in active_unadded:
            alias = r.hostname if r.hostname else f"PC {r.ip}"
            new_h = Host(
                alias=alias,
                ip=r.ip,
                port=r.port,
                group="Default",
                notes="Ditemukan via Pemindai Jaringan"
            )
            self.db.add_host(new_h)
            self.existing_hosts_set.add((r.ip, r.port))
            self.checked_keys.discard(f"{r.ip}:{r.port}")
            added_count += 1

        self._refresh_results_table()
        self._update_action_counts()

        if self.on_hosts_added:
            self.on_hosts_added()

        messagebox.showinfo("Berhasil", f"Berhasil menambahkan {added_count} host ke dalam grup 'Default'.", parent=self)

    def _on_closing(self):
        self.scanner.stop()
        self.destroy()
