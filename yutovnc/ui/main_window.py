"""Main Application Window for YutoVNC."""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import ipaddress
import os
import threading
from dataclasses import replace
from typing import Optional, List, Dict
from datetime import datetime

from yutovnc.models import Host, AppSettings, HostStatus
from yutovnc.database import Database
from yutovnc.monitor import StatusMonitor
from yutovnc.vnc_launcher import SessionManager, Session, normalize_scaling_mode
from yutovnc.theme import apply_theme, get_theme_colors
from yutovnc.paths import get_resource_path
from yutovnc.ui.host_dialog import HostDialog
from yutovnc.ui.settings_dialog import SettingsDialog
from yutovnc.ui.import_export_dialog import ImportExportDialog
from yutovnc.ui.session_tab import SessionTab
from yutovnc.ui.scanner_dialog import ScannerDialog

class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("YutoVNC - Smart Remote Client")
        self.geometry("1100x680")
        self.minsize(900, 550)

        # Initialize core components
        self.db = Database()
        self.settings: AppSettings = self.db.get_all_settings()
        self.monitor = StatusMonitor()
        self.session_mgr = SessionManager()

        # State tracking
        self.colors = apply_theme(self, self.settings.theme)
        self._set_app_icon()
        self.active_session_tabs: Dict[str, SessionTab] = {}
        self.selected_group_filter = "All"
        self.hosts_cache: List[Host] = []
        self._sort_column: Optional[str] = None
        self._sort_descending: bool = False

        self._init_ui()
        self._setup_monitor()
        self.refresh_host_list()
        self.refresh_group_sidebar()
        self.center_window()

        # Handle window close
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

    def center_window(self):
        self.update_idletasks()
        w = 1100
        h = 680
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _set_app_icon(self):
        icon_path = get_resource_path(os.path.join("assets", "icon.ico"))
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

    def _init_ui(self):
        # 1. Top Header Bar
        header = ttk.Frame(self, style="Sidebar.TFrame", padding=(16, 10))
        header.pack(fill="x", side="top")

        # Brand / Title
        brand_frame = ttk.Frame(header, style="Sidebar.TFrame")
        brand_frame.pack(side="left")
        ttk.Label(brand_frame, text="⚡ YutoVNC", font=("Segoe UI", 14, "bold"), foreground=self.colors["accent"]).pack(side="left")
        ttk.Label(brand_frame, text=" | Smart Remote Client", font=("Segoe UI", 10), style="Muted.TLabel").pack(side="left", padx=(4, 16))

        # Action Buttons on Header
        actions_frame = ttk.Frame(header, style="Sidebar.TFrame")
        actions_frame.pack(side="right")

        ttk.Button(actions_frame, text="➕ Tambah Host", style="Primary.TButton", command=self._open_add_host_dialog).pack(side="left", padx=3)
        ttk.Button(actions_frame, text="📡 Scan Jaringan", command=self._open_scanner_dialog).pack(side="left", padx=3)
        ttk.Button(actions_frame, text="⚡ 1-Klik Masuk", style="Success.TButton", command=self._connect_selected).pack(side="left", padx=3)
        ttk.Button(actions_frame, text="🔄 Cek Status", command=self._check_all_statuses).pack(side="left", padx=3)
        ttk.Button(actions_frame, text="📁 Backup", command=self._open_import_export_dialog).pack(side="left", padx=3)
        ttk.Button(actions_frame, text="⚙️ Pengaturan", command=self._open_settings_dialog).pack(side="left", padx=3)

        # 2. Main Tabbed Notebook (Multi-Session Tabs)
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=4)
        self.notebook.bind("<Button-1>", self._on_notebook_click)
        self.notebook.bind("<Button-2>", self._on_notebook_middle_click)
        self.notebook.bind("<Button-3>", self._on_notebook_right_click)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_notebook_tab_changed)
        self.bind("<Control-w>", self._close_current_session_tab)
        self.bind("<Control-W>", self._close_current_session_tab)
        self.bind("<Control-F4>", self._close_current_session_tab)

        self._build_tab_context_menu()

        # Primary Tab: Address Book
        self.address_book_tab = ttk.Frame(self.notebook, style="TFrame")
        self.notebook.add(self.address_book_tab, text="📋 Daftar Host (Address Book)")

        self._build_address_book_tab(self.address_book_tab)

        # 3. Status Bar at bottom
        self.status_bar = ttk.Frame(self, style="Sidebar.TFrame", padding=(12, 4))
        self.status_bar.pack(fill="x", side="bottom")

        self.status_lbl = ttk.Label(self.status_bar, text="Siap", style="Muted.TLabel")
        self.status_lbl.pack(side="left")

        self.stats_lbl = ttk.Label(self.status_bar, text="Total: 0 Host", style="Muted.TLabel")
        self.stats_lbl.pack(side="right", padx=(10, 0))

        viewer_name = os.path.basename(self.settings.vnc_viewer_path)
        self.viewer_lbl = ttk.Label(self.status_bar, text=f"Engine: {viewer_name}", style="Muted.TLabel")
        self.viewer_lbl.pack(side="right", padx=10)

    def _build_address_book_tab(self, parent: ttk.Frame):
        paned = ttk.PanedWindow(parent, orient="horizontal")
        paned.pack(fill="both", expand=True)

        # Left Sidebar: Group filter & categories
        sidebar = ttk.Frame(paned, style="Sidebar.TFrame", padding=10, width=220)
        paned.add(sidebar, weight=1)

        ttk.Label(sidebar, text="KATEGORI & GRUP", font=("Segoe UI", 9, "bold"), style="Muted.TLabel").pack(anchor="w", pady=(2, 8))

        # Group Listbox / Treeview
        self.group_tree = ttk.Treeview(sidebar, show="tree", selectmode="browse")
        self.group_tree.pack(fill="both", expand=True)
        self.group_tree.bind("<<TreeviewSelect>>", self._on_group_selected)
        self.group_tree.bind("<Button-3>", self._show_group_context_menu)
        self.group_tree.bind("<F2>", lambda _e: self._rename_group_prompt())

        self._build_group_context_menu()

        # Group Action Buttons
        grp_btn_frame = ttk.Frame(sidebar, style="Sidebar.TFrame")
        grp_btn_frame.pack(fill="x", pady=(8, 0))
        ttk.Button(grp_btn_frame, text="+ Grup", command=self._add_group_prompt).pack(side="left", fill="x", expand=True, padx=(0, 2))
        ttk.Button(grp_btn_frame, text="✏️", width=3, style="Small.TButton", command=self._rename_group_prompt).pack(side="left", padx=(0, 2))
        ttk.Button(grp_btn_frame, text="🗑️", width=3, style="Small.TButton", command=self._delete_group_prompt).pack(side="right")

        # Right Pane: Host Table
        table_frame = ttk.Frame(paned, style="TFrame", padding=(8, 10, 10, 10))
        paned.add(table_frame, weight=5)

        # Search Bar inside Address Book tab (above host table)
        search_frame = ttk.Frame(table_frame, style="TFrame")
        search_frame.pack(fill="x", pady=(0, 8))

        ttk.Label(search_frame, text="🔍 Cari:", style="Muted.TLabel").pack(side="left", padx=(0, 6))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh_host_list())

        # Clear search button (packed before entry so it never gets clipped)
        self.clear_search_btn = ttk.Button(
            search_frame,
            text="✕",
            width=3,
            style="Small.TButton",
            takefocus=False,
            command=self._clear_search
        )
        self.clear_search_btn.pack(side="right", padx=(6, 0))

        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        self.search_entry.pack(side="left", fill="x", expand=True)
        self.search_entry.bind("<Escape>", self._clear_search)
        self.search_entry.bind("<Button-1>", self._on_search_entry_click, add="+")

        # Table Filter Sub-bar
        subbar = ttk.Frame(table_frame, style="TFrame")
        subbar.pack(fill="x", pady=(0, 6))

        self.filter_lbl = ttk.Label(subbar, text="Menampilkan Semua Host", font=("Segoe UI", 10, "bold"), style="TLabel")
        self.filter_lbl.pack(side="left")

        # Quick filter toggle (Online only)
        self.online_only_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            subbar,
            text="Hanya yang Online 🟢",
            variable=self.online_only_var,
            command=self.refresh_host_list
        ).pack(side="right")

        # Treeview Container
        tree_container = ttk.Frame(table_frame, style="TFrame")
        tree_container.pack(fill="both", expand=True)

        # Treeview Columns
        columns = ("fav", "status", "alias", "ip", "port", "group", "mode", "last", "notes")
        self._host_column_headers = {
            "fav": "⭐",
            "status": "Status",
            "alias": "Nama Alias / Ruangan",
            "ip": "IP Address",
            "port": "Port",
            "group": "Grup / Kategori",
            "mode": "Mode Tampilan",
            "last": "Terakhir Terhubung",
            "notes": "Catatan",
        }
        self.host_tree = ttk.Treeview(tree_container, columns=columns, show="headings", selectmode="extended")

        for col_id, col_title in self._host_column_headers.items():
            self.host_tree.heading(
                col_id,
                text=col_title,
                command=lambda c=col_id: self._on_host_column_click(c)
            )

        self.host_tree.column("fav", width=40, anchor="center", stretch=False)
        self.host_tree.column("status", width=120, anchor="w", stretch=False)
        self.host_tree.column("alias", width=190, anchor="w")
        self.host_tree.column("ip", width=130, anchor="w")
        self.host_tree.column("port", width=65, anchor="center", stretch=False)
        self.host_tree.column("group", width=120, anchor="w")
        self.host_tree.column("mode", width=110, anchor="w")
        self.host_tree.column("last", width=140, anchor="w")
        self.host_tree.column("notes", width=160, anchor="w")

        # Scrollbar
        scrollbar = ttk.Scrollbar(tree_container, orient="vertical", command=self.host_tree.yview)
        self.host_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.host_tree.pack(side="left", fill="both", expand=True)

        # Bind events
        # Double click -> 1-Click Connect immediately!
        self.host_tree.bind("<Double-1>", lambda _: self._connect_selected())
        # Right click -> Context menu
        self.host_tree.bind("<Button-3>", self._show_context_menu)
        # Enter key -> Connect
        self.host_tree.bind("<Return>", lambda _: self._connect_selected())
        # Delete key -> Delete
        self.host_tree.bind("<Delete>", lambda _: self._delete_selected_host())

        self._build_context_menu()

    def _build_context_menu(self):
        self.context_menu = tk.Menu(self, tearoff=0, bg=self.colors["surface"], fg=self.colors["text"], activebackground=self.colors["accent"], activeforeground="#ffffff")
        self.context_menu.add_command(label="⚡ 1-Klik Masuk (Auto-Login)", font=("Segoe UI", 9, "bold"), command=self._connect_selected)
        self.context_menu.add_command(label="🔲 Masuk di Tab Baru (Embedded)", command=lambda: self._connect_selected(force_embed=True))
        self.context_menu.add_command(label="↗️ Masuk di Jendela Terpisah", command=lambda: self._connect_selected(force_embed=False))
        self.context_menu.add_separator()
        self.context_menu.add_command(label="✏️ Edit Host...", command=self._edit_selected_host)
        self.context_menu.add_command(label="⭐ Tandai / Hapus Favorit", command=self._toggle_favorite_selected)
        self.context_menu.add_command(label="🔍 Cek Port 5900 Sekarang", command=self._check_selected_status)
        self.context_menu.add_command(label="📋 Salin IP Address", command=self._copy_selected_ip)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="🗑️ Hapus Host", command=self._delete_selected_host)

    def _show_context_menu(self, event):
        item = self.host_tree.identify_row(event.y)
        if item:
            if item not in self.host_tree.selection():
                self.host_tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)

    def _build_group_context_menu(self):
        self.group_context_menu = tk.Menu(
            self, tearoff=0,
            bg=self.colors["surface"], fg=self.colors["text"],
            activebackground=self.colors["accent"], activeforeground="#ffffff"
        )
        self.group_context_menu.add_command(label="➕ Tambah Grup Baru...", command=self._add_group_prompt)
        self.group_context_menu.add_command(label="✏️ Rename Grup...", command=self._rename_group_prompt)
        self.group_context_menu.add_separator()
        self.group_context_menu.add_command(label="🗑️ Hapus Grup", command=self._delete_group_prompt)

    def _show_group_context_menu(self, event):
        item = self.group_tree.identify_row(event.y)
        if item:
            self.group_tree.selection_set(item)
            self._on_group_selected(None)
            self.group_context_menu.post(event.x_root, event.y_root)

    def _build_tab_context_menu(self):
        self._right_clicked_tab_idx: Optional[int] = None
        self.tab_context_menu = tk.Menu(
            self, tearoff=0,
            bg=self.colors["surface"], fg=self.colors["text"],
            activebackground=self.colors["accent"], activeforeground="#ffffff"
        )
        self.tab_context_menu.add_command(
            label="❌ Tutup Tab & Putuskan VNC",
            command=lambda: self._close_tab_by_index(self._right_clicked_tab_idx)
        )

    def _on_search_entry_click(self, _event=None):
        """Release any embedded VNC thread input and force focus onto search input."""
        self._release_all_vnc_focus(except_tab=None)
        self.search_entry.focus_force()

    def _clear_search(self, _event=None):
        """Clear search bar text, restore focus, and reset host list filter."""
        self._release_all_vnc_focus(except_tab=None)
        self.search_entry.delete(0, tk.END)
        if self.search_var.get() != "":
            self.search_var.set("")
        self.refresh_host_list()
        self.search_entry.focus_force()
        self.search_entry.icursor(tk.END)

    def _on_notebook_click(self, event):
        """Detect click on the '✕' close area of any session tab."""
        try:
            idx = self.notebook.index(f"@{event.x},{event.y}")
        except tk.TclError:
            return
        if idx <= 0:
            return
        right_x = event.x
        nb_width = max(event.x + 40, self.notebook.winfo_width())
        while right_x < nb_width:
            try:
                if self.notebook.index(f"@{right_x},{event.y}") != idx:
                    break
            except tk.TclError:
                break
            right_x += 2
        if right_x - event.x <= 28:
            self._close_tab_by_index(idx)
            return "break"

    def _on_notebook_middle_click(self, event):
        try:
            idx = self.notebook.index(f"@{event.x},{event.y}")
        except tk.TclError:
            return
        if idx > 0:
            self._close_tab_by_index(idx)
            return "break"

    def _on_notebook_right_click(self, event):
        try:
            idx = self.notebook.index(f"@{event.x},{event.y}")
        except tk.TclError:
            return
        if idx > 0:
            self._right_clicked_tab_idx = idx
            self.tab_context_menu.post(event.x_root, event.y_root)

    def _release_all_vnc_focus(self, except_tab: Optional[SessionTab] = None):
        """Detach Win32 thread input from active embedded VNC sessions."""
        for tab in list(self.active_session_tabs.values()):
            if tab is not except_tab:
                try:
                    tab.release_focus()
                except Exception:
                    pass

    def _on_notebook_tab_changed(self, _event=None):
        """Detach VNC thread input on Address Book tab, or re-attach and focus VNC on session tab."""
        try:
            current_widget_name = self.notebook.select()
            if not current_widget_name:
                return
            tab_widget = self.nametowidget(current_widget_name)
            if isinstance(tab_widget, SessionTab):
                self._release_all_vnc_focus(except_tab=tab_widget)
                self.after(50, tab_widget.focus_vnc)
            else:
                self._release_all_vnc_focus(except_tab=None)
                self.focus_force()
        except Exception:
            pass

    def _close_current_session_tab(self, _event=None):
        try:
            idx = self.notebook.index("current")
        except tk.TclError:
            return
        if idx > 0:
            self._close_tab_by_index(idx)
            return "break"

    def _close_tab_by_index(self, idx: Optional[int]):
        if idx is None or idx <= 0:
            return
        tabs = self.notebook.tabs()
        if idx >= len(tabs):
            return
        tab_widget = self.nametowidget(tabs[idx])
        if isinstance(tab_widget, SessionTab):
            tab_widget.close_session_tab(confirm=False)

    # --- Data Loading & Refreshing ---

    def refresh_group_sidebar(self):
        """Populate groups in left sidebar with counts."""
        for item in self.group_tree.get_children():
            self.group_tree.delete(item)

        hosts = self.db.get_all_hosts()
        total_count = len(hosts)
        fav_count = sum(1 for h in hosts if h.is_favorite)

        # Standard root entries
        all_node = self.group_tree.insert("", "end", iid="ALL", text=f"💻 Semua Host ({total_count})")
        fav_node = self.group_tree.insert("", "end", iid="FAV", text=f"⭐ Favorit ({fav_count})")

        # Custom groups
        groups = self.db.get_groups()
        for g in groups:
            count = sum(1 for h in hosts if h.group == g)
            self.group_tree.insert("", "end", iid=f"GRP_{g}", text=f"📁 {g} ({count})")

        # Select current
        if self.selected_group_filter == "All":
            self.group_tree.selection_set("ALL")
        elif self.selected_group_filter == "Favorites":
            self.group_tree.selection_set("FAV")
        elif f"GRP_{self.selected_group_filter}" in self.group_tree.get_children():
            self.group_tree.selection_set(f"GRP_{self.selected_group_filter}")

    def _format_host_mode(self, host: Host) -> str:
        mode_parts = []
        if host.view_only:
            mode_parts.append("Hanya Lihat")
        if host.fullscreen:
            mode_parts.append("Layar Penuh")
        if not mode_parts:
            mode_parts.append("Normal")
        return ", ".join(mode_parts)

    def _host_sort_key(self, host: Host, status: Optional[HostStatus], col_id: str):
        """Return sortable key for a host row according to the active column."""
        if col_id == "fav":
            return (1 if host.is_favorite else 0, host.alias.lower())
        if col_id == "status":
            if status and status.online:
                return (0, float(status.latency_ms), host.alias.lower())
            if status and not status.online:
                return (1, 0.0, host.alias.lower())
            return (2, 0.0, host.alias.lower())
        if col_id == "alias":
            return (host.alias.lower(), host.ip.lower(), int(host.port or 5900))
        if col_id == "ip":
            raw_ip = host.ip.strip()
            try:
                ip_obj = ipaddress.ip_address(raw_ip)
                return (0, ip_obj.version, int(ip_obj), int(host.port or 5900))
            except ValueError:
                return (1, 0, raw_ip.lower(), int(host.port or 5900))
        if col_id == "port":
            return (int(host.port or 5900), host.alias.lower())
        if col_id == "group":
            return (host.group.lower(), host.alias.lower())
        if col_id == "mode":
            return (self._format_host_mode(host).lower(), host.alias.lower())
        if col_id == "last":
            return (host.last_connected_at or "", host.alias.lower())
        if col_id == "notes":
            return (host.notes.lower(), host.alias.lower())
        return (host.alias.lower(),)

    def _update_column_sort_indicators(self):
        """Update Treeview column headings with active sort arrow indicator."""
        for col_id, base_title in self._host_column_headers.items():
            if col_id == self._sort_column:
                arrow = " ▼" if self._sort_descending else " ▲"
                self.host_tree.heading(col_id, text=f"{base_title}{arrow}")
            else:
                self.host_tree.heading(col_id, text=base_title)

    def _on_host_column_click(self, col_id: str):
        """Toggle ASC/DESC sort order when clicking a host table column header."""
        if self._sort_column == col_id:
            self._sort_descending = not self._sort_descending
        else:
            self._sort_column = col_id
            self._sort_descending = False
        self._update_column_sort_indicators()
        self.refresh_host_list()

    def refresh_host_list(self):
        """Refresh the host table with current search, group, status filter, and sort order."""
        for item in self.host_tree.get_children():
            self.host_tree.delete(item)

        query = self.search_var.get().strip()
        fav_only = self.selected_group_filter == "Favorites"
        grp_filter = None if self.selected_group_filter in ("All", "Favorites") else self.selected_group_filter

        hosts = self.db.get_all_hosts(search_query=query, group_filter=grp_filter, favorites_only=fav_only)
        self.hosts_cache = hosts

        online_filter = self.online_only_var.get()
        online_count = 0
        offline_count = 0
        visible_rows = []

        for h in hosts:
            st = self.monitor.get_status(h.id)
            if st and st.online:
                online_count += 1
                status_text = f"🟢 {st.latency_ms} ms"
            elif st and not st.online:
                offline_count += 1
                status_text = "🔴 Offline"
            else:
                status_text = "⚪ Belum dicek"

            if online_filter and (st is None or not st.online):
                continue

            visible_rows.append((h, st, status_text))

        if self._sort_column:
            visible_rows.sort(
                key=lambda row: self._host_sort_key(row[0], row[1], self._sort_column),
                reverse=self._sort_descending
            )

        for h, _st, status_text in visible_rows:
            fav_icon = "⭐" if h.is_favorite else ""
            mode_str = self._format_host_mode(h)
            last_conn = h.last_connected_at or "-"

            self.host_tree.insert(
                "",
                "end",
                iid=str(h.id),
                values=(
                    fav_icon,
                    status_text,
                    h.alias,
                    h.ip,
                    str(h.port),
                    h.group,
                    mode_str,
                    last_conn,
                    h.notes
                )
            )

        # Update stats in status bar
        self.stats_lbl.configure(text=f"Total: {len(hosts)} Host | 🟢 {online_count} Online | 🔴 {offline_count} Offline")
        title_grp = self.selected_group_filter
        if title_grp == "All":
            self.filter_lbl.configure(text="Menampilkan Semua Host")
        elif title_grp == "Favorites":
            self.filter_lbl.configure(text="Menampilkan Host Favorit ⭐")
        else:
            self.filter_lbl.configure(text=f"Menampilkan Grup: {title_grp}")

    def _on_group_selected(self, _):
        selected = self.group_tree.selection()
        if not selected:
            return
        node_id = selected[0]
        if node_id == "ALL":
            self.selected_group_filter = "All"
        elif node_id == "FAV":
            self.selected_group_filter = "Favorites"
        elif node_id.startswith("GRP_"):
            self.selected_group_filter = node_id[4:]
        self.refresh_host_list()

    def _setup_monitor(self):
        """Set up status callbacks and auto-polling."""
        def on_status_update(host_id: int, status: HostStatus):
            # Update row in treeview on UI thread
            def ui_update():
                item_id = str(host_id)
                if self.host_tree.exists(item_id):
                    current_values = list(self.host_tree.item(item_id, "values"))
                    if len(current_values) >= 8:
                        if status.online:
                            current_values[1] = f"🟢 {status.latency_ms} ms"
                        else:
                            current_values[1] = "🔴 Offline"
                        self.host_tree.item(item_id, values=current_values)
            self.after(0, ui_update)

        self.monitor.register_callback(on_status_update)

        # Start auto polling if configured
        if self.settings.auto_refresh_interval > 0:
            self.monitor.start_polling(self.db.get_all_hosts, self.settings.auto_refresh_interval)

    # --- Connection & Sessions ---

    def _connect_selected(self, force_embed: Optional[bool] = None):
        """One-Click Connect: Launch remote session with auto-login."""
        selected = self.host_tree.selection()
        if not selected:
            messagebox.showinfo("Pilih Host", "Silakan pilih salah satu host dari daftar.", parent=self)
            return

        host_id = int(selected[0])
        host = self.db.get_host_by_id(host_id)
        if not host:
            return

        self._launch_host_session(host, force_embed=force_embed)

    def _launch_host_session(self, host: Host, force_embed: Optional[bool] = None):
        """Connect to host either in embedded tab or external window."""
        embed = self.settings.embed_in_tab if force_embed is None else force_embed

        self.status_lbl.configure(text=f"Menghubungkan ke '{host.alias}' ({host.ip}:{host.port})...")
        self.db.update_last_connected(host.id)

        if embed:
            # Create session tab first so we have the container HWND
            session_tab = None

            def on_tab_closed(tab: SessionTab, popped_out: bool = False):
                sid = tab.session.session_id
                if sid in self.active_session_tabs:
                    del self.active_session_tabs[sid]
                if not popped_out:
                    self.session_mgr.close_session(sid)
                # Remove tab from notebook and destroy widget to free memory & handles
                try:
                    self.notebook.forget(tab)
                except Exception:
                    pass
                try:
                    tab.destroy()
                except Exception:
                    pass
                if popped_out:
                    self.status_lbl.configure(text=f"Sesi '{host.alias}' dipindahkan ke jendela eksternal.")
                else:
                    self.status_lbl.configure(text=f"Sesi dengan '{host.alias}' diputuskan.")
                    self.monitor.check_host_async(host)

            def on_reconnect(h: Host):
                self._launch_host_session(h, force_embed=True)

            def _safe_ui(fn):
                try:
                    self.after(0, fn)
                except RuntimeError:
                    pass

            def on_in_place_reconnect(tab: SessionTab, view_only: bool, is_scaled: bool):
                old_sid = tab.session.session_id
                if old_sid in self.active_session_tabs:
                    del self.active_session_tabs[old_sid]
                self.session_mgr.close_session(old_sid)

                scale_fit = (tab.current_scale_mode == "fit") if hasattr(tab, "current_scale_mode") else is_scaled
                run_host = replace(
                    tab.session.host,
                    view_only=view_only,
                    scaling="auto" if scale_fit else "100%"
                )
                container_hwnd = tab.get_container_hwnd()
                cw, ch = tab.get_container_size()
                try:
                    new_session = self.session_mgr.launch_host(
                        run_host,
                        self.settings,
                        container_hwnd=container_hwnd,
                        container_width=cw,
                        container_height=ch,
                        on_embedded_ready=lambda s: _safe_ui(lambda sess=s: tab.on_window_embedded(sess)),
                        on_error=lambda err: _safe_ui(lambda: messagebox.showerror("Gagal Koneksi", err, parent=self))
                    )
                    new_session.is_scaled = scale_fit
                    new_session.is_view_only = view_only
                    tab.session = new_session
                    self.active_session_tabs[new_session.session_id] = tab
                except Exception as e:
                    messagebox.showerror("Gagal Koneksi", f"Tidak dapat menyambung ulang: {e}", parent=self)

            # Default Scale to Fit unless host explicitly specifies "100%"
            launch_host = replace(host, scaling="100%" if normalize_scaling_mode(host.scaling) == "100%" else "auto")
            temp_session = Session(launch_host, None, is_embedded=True)
            session_tab = SessionTab(
                self.notebook,
                temp_session,
                self.settings,
                on_close=on_tab_closed,
                on_reconnect=on_reconnect,
                on_in_place_reconnect=on_in_place_reconnect,
                theme_name=self.settings.theme
            )
            tab_title = f"🖥️ {host.alias}   ✕"
            self.notebook.add(session_tab, text=tab_title)
            self.notebook.select(session_tab)

            container_hwnd = session_tab.get_container_hwnd()
            w, h = session_tab.get_container_size()

            try:
                real_session = self.session_mgr.launch_host(
                    launch_host,
                    self.settings,
                    container_hwnd=container_hwnd,
                    container_width=w,
                    container_height=h,
                    on_embedded_ready=lambda s: _safe_ui(lambda sess=s: session_tab.on_window_embedded(sess)),
                    on_error=lambda err: _safe_ui(lambda: messagebox.showerror("Gagal Koneksi", err, parent=self))
                )
                session_tab.session = real_session
                self.active_session_tabs[real_session.session_id] = session_tab
                self.status_lbl.configure(text=f"🟢 Terhubung ke '{host.alias}'")
            except Exception as e:
                try:
                    self.notebook.forget(session_tab)
                    session_tab.destroy()
                except Exception:
                    pass
                messagebox.showerror("Gagal Koneksi", f"Tidak dapat membuka sesi VNC: {e}", parent=self)
        else:
            # Standalone External Window mode
            launch_host = replace(host, scaling="100%" if normalize_scaling_mode(host.scaling) == "100%" else "auto")
            try:
                self.session_mgr.launch_host(
                    launch_host,
                    self.settings,
                    container_hwnd=None,
                    on_error=lambda err: self.after(0, lambda: messagebox.showerror("Gagal Koneksi", err, parent=self))
                )
                self.status_lbl.configure(text=f"🟢 Sesi '{host.alias}' dibuka di jendela baru.")
            except Exception as e:
                messagebox.showerror("Gagal Koneksi", f"Gagal menjalankan VNC Viewer: {e}", parent=self)

        # Refresh last connected column
        self.refresh_host_list()

    # --- Host CRUD Dialogs ---

    def _open_add_host_dialog(self):
        HostDialog(
            self,
            self.db,
            self.monitor,
            host=None,
            on_saved=self._on_host_saved,
            theme_name=self.settings.theme
        )

    def _edit_selected_host(self):
        selected = self.host_tree.selection()
        if not selected:
            return
        h_id = int(selected[0])
        host = self.db.get_host_by_id(h_id)
        if host:
            HostDialog(
                self,
                self.db,
                self.monitor,
                host=host,
                on_saved=self._on_host_saved,
                theme_name=self.settings.theme
            )

    def _on_host_saved(self, host: Host):
        self.refresh_host_list()
        self.refresh_group_sidebar()
        self.monitor.check_host_async(host)
        self.status_lbl.configure(text=f"Host '{host.alias}' berhasil disimpan.")

    def _delete_selected_host(self):
        selected = self.host_tree.selection()
        if not selected:
            return
        h_id = int(selected[0])
        host = self.db.get_host_by_id(h_id)
        if not host:
            return
        if messagebox.askyesno("Konfirmasi Hapus", f"Apakah Anda yakin ingin menghapus host '{host.alias}' ({host.ip})?", parent=self):
            self.db.delete_host(h_id)
            self.refresh_host_list()
            self.refresh_group_sidebar()
            self.status_lbl.configure(text=f"Host '{host.alias}' dihapus.")

    def _toggle_favorite_selected(self):
        selected = self.host_tree.selection()
        if not selected:
            return
        h_id = int(selected[0])
        self.db.toggle_favorite(h_id)
        self.refresh_host_list()
        self.refresh_group_sidebar()

    def _check_selected_status(self):
        selected = self.host_tree.selection()
        if not selected:
            return
        h_id = int(selected[0])
        host = self.db.get_host_by_id(h_id)
        if host:
            self.status_lbl.configure(text=f"Memeriksa status {host.alias}...")
            self.monitor.check_host_async(host)

    def _check_all_statuses(self):
        self.status_lbl.configure(text="Sedang memeriksa port 5900 seluruh host...")
        hosts = self.db.get_all_hosts()
        self.monitor.check_all_hosts_async(hosts)

    def _copy_selected_ip(self):
        selected = self.host_tree.selection()
        if not selected:
            return
        h_id = int(selected[0])
        host = self.db.get_host_by_id(h_id)
        if host:
            self.clipboard_clear()
            self.clipboard_append(host.ip)
            self.status_lbl.configure(text=f"IP {host.ip} disalin ke clipboard.")

    # --- Group Management ---

    def _add_group_prompt(self):
        name = simpledialog.askstring("Grup Baru", "Masukkan nama grup / kategori baru:", parent=self)
        if name and name.strip():
            self.db.add_group(name.strip())
            self.refresh_group_sidebar()

    def _rename_group_prompt(self):
        if self.selected_group_filter in ("All", "Favorites", "Default"):
            messagebox.showinfo("Perhatian", "Grup bawaan ini tidak dapat diubah namanya.", parent=self)
            return
        old_name = self.selected_group_filter
        new_name = simpledialog.askstring(
            "Rename Grup",
            f"Masukkan nama baru untuk grup '{old_name}':",
            initialvalue=old_name,
            parent=self
        )
        if not new_name or not new_name.strip():
            return
        new_name = new_name.strip()
        if new_name == old_name:
            return
        if new_name in self.db.get_groups():
            messagebox.showwarning("Perhatian", f"Nama grup '{new_name}' sudah digunakan.", parent=self)
            return
        if self.db.rename_group(old_name, new_name):
            self.selected_group_filter = new_name
            self.refresh_group_sidebar()
            self.refresh_host_list()
            self.status_lbl.configure(text=f"Grup '{old_name}' berhasil diubah menjadi '{new_name}'.")
        else:
            messagebox.showerror("Gagal", f"Tidak dapat mengubah nama grup '{old_name}'.", parent=self)

    def _delete_group_prompt(self):
        if self.selected_group_filter in ("All", "Favorites", "Default"):
            messagebox.showinfo("Perhatian", "Grup bawaan ini tidak dapat dihapus.", parent=self)
            return
        grp = self.selected_group_filter
        if messagebox.askyesno("Hapus Grup", f"Hapus grup '{grp}'? Host di dalamnya akan dipindahkan ke 'Default'.", parent=self):
            self.db.delete_group(grp)
            self.selected_group_filter = "All"
            self.refresh_group_sidebar()
            self.refresh_host_list()

    def _open_scanner_dialog(self):
        ScannerDialog(
            self,
            self.db,
            monitor=self.monitor,
            on_hosts_added=self._on_scanner_hosts_added,
            theme_name=self.settings.theme
        )

    def _on_scanner_hosts_added(self):
        if self.selected_group_filter not in ("All", "Default"):
            self.selected_group_filter = "Default"
        self.refresh_group_sidebar()
        self.refresh_host_list()
        self.status_lbl.configure(text="Host hasil scan berhasil ditambahkan ke grup 'Default'.")
        self.monitor.check_all_hosts_async(self.db.get_all_hosts())

    # --- Settings & Import/Export Dialogs ---

    def _open_settings_dialog(self):
        SettingsDialog(
            self,
            self.db,
            self.settings,
            on_saved=self._on_settings_saved,
            theme_name=self.settings.theme
        )

    def _on_settings_saved(self, new_settings: AppSettings):
        self.settings = new_settings
        self.colors = apply_theme(self, self.settings.theme)
        self.viewer_lbl.configure(text=f"Engine: {os.path.basename(self.settings.vnc_viewer_path)}")
        # Restart monitor polling with new interval
        if self.settings.auto_refresh_interval > 0:
            self.monitor.start_polling(self.db.get_all_hosts, self.settings.auto_refresh_interval)
        else:
            self.monitor.stop_polling()
        self.refresh_host_list()

    def _open_import_export_dialog(self):
        ImportExportDialog(
            self,
            self.db,
            on_data_changed=lambda: (self.refresh_host_list(), self.refresh_group_sidebar()),
            theme_name=self.settings.theme
        )

    def _on_closing(self):
        """Clean shutdown of background threads and sessions."""
        self.monitor.shutdown()
        self.session_mgr.close_all()
        self.destroy()
