"""SQLite database manager for YutoVNC.

Features:
- Thread-safe connection handling
- WAL (Write-Ahead Logging) mode for maximum performance & crash resistance
- Fast indexed search over alias, IP, group, and notes
- Automatic migrations and default settings initialization
"""

import sqlite3
import os
from typing import List, Optional, Dict, Any
from datetime import datetime
from yutovnc.models import Host, AppSettings
from yutovnc.paths import get_database_path, get_default_screenshots_dir

class Database:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or get_database_path()
        self._init_db()

    from contextlib import contextmanager

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        """Initialize tables and indexes."""
        with self._connection() as conn:
            # Groups table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    color TEXT DEFAULT '#3b82f6',
                    sort_order INTEGER DEFAULT 0
                )
            """)

            # Hosts table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hosts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alias TEXT NOT NULL,
                    ip TEXT NOT NULL,
                    port INTEGER NOT NULL DEFAULT 5900,
                    group_name TEXT NOT NULL DEFAULT 'Default',
                    password_enc TEXT DEFAULT '',
                    view_only INTEGER NOT NULL DEFAULT 0,
                    fullscreen INTEGER NOT NULL DEFAULT 0,
                    scaling TEXT DEFAULT 'auto',
                    notes TEXT DEFAULT '',
                    is_favorite INTEGER NOT NULL DEFAULT 0,
                    sort_order INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_connected_at TEXT
                )
            """)

            # Indexes for lightning-fast search
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hosts_alias ON hosts(alias)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hosts_ip ON hosts(ip)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hosts_group ON hosts(group_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hosts_fav ON hosts(is_favorite)")

            # Settings table (key-value)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

            # Populate default groups if empty
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) as count FROM groups")
            if cur.fetchone()["count"] == 0:
                defaults = [("Default", "#3b82f6", 0), ("Server IT", "#10b981", 1), ("Lab Komputer", "#f59e0b", 2), ("Kasir / POS", "#8b5cf6", 3)]
                cur.executemany("INSERT INTO groups (name, color, sort_order) VALUES (?, ?, ?)", defaults)

            conn.commit()

    # --- Host CRUD Operations ---

    def add_host(self, host: Host) -> int:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        host.created_at = now
        host.updated_at = now
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO hosts (
                    alias, ip, port, group_name, password_enc,
                    view_only, fullscreen, scaling, notes,
                    is_favorite, sort_order, created_at, updated_at, last_connected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                host.alias.strip(),
                host.ip.strip(),
                host.port or 5900,
                host.group.strip() or "Default",
                host.password_enc or "",
                1 if host.view_only else 0,
                1 if host.fullscreen else 0,
                host.scaling or "auto",
                host.notes or "",
                1 if host.is_favorite else 0,
                host.sort_order,
                host.created_at,
                host.updated_at,
                host.last_connected_at
            ))
            conn.commit()
            return cur.lastrowid

    def update_host(self, host: Host) -> bool:
        if not host.id:
            return False
        host.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE hosts SET
                    alias = ?,
                    ip = ?,
                    port = ?,
                    group_name = ?,
                    password_enc = ?,
                    view_only = ?,
                    fullscreen = ?,
                    scaling = ?,
                    notes = ?,
                    is_favorite = ?,
                    sort_order = ?,
                    updated_at = ?
                WHERE id = ?
            """, (
                host.alias.strip(),
                host.ip.strip(),
                host.port or 5900,
                host.group.strip() or "Default",
                host.password_enc or "",
                1 if host.view_only else 0,
                1 if host.fullscreen else 0,
                host.scaling or "auto",
                host.notes or "",
                1 if host.is_favorite else 0,
                host.sort_order,
                host.updated_at,
                host.id
            ))
            conn.commit()
            return cur.rowcount > 0

    def delete_host(self, host_id: int) -> bool:
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM hosts WHERE id = ?", (host_id,))
            conn.commit()
            return cur.rowcount > 0

    def get_host_by_id(self, host_id: int) -> Optional[Host]:
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM hosts WHERE id = ?", (host_id,))
            row = cur.fetchone()
            if row:
                return Host.from_row(row)
            return None

    def get_all_hosts(
        self,
        search_query: Optional[str] = None,
        group_filter: Optional[str] = None,
        favorites_only: bool = False
    ) -> List[Host]:
        """Fetch hosts with optional instant search & category filtering."""
        query = "SELECT * FROM hosts WHERE 1=1"
        params: List[Any] = []

        if favorites_only:
            query += " AND is_favorite = 1"

        if group_filter and group_filter not in ("All", "Semua"):
            query += " AND group_name = ?"
            params.append(group_filter)

        if search_query:
            term = f"%{search_query.strip()}%"
            query += " AND (alias LIKE ? OR ip LIKE ? OR group_name LIKE ? OR notes LIKE ?)"
            params.extend([term, term, term, term])

        query += " ORDER BY is_favorite DESC, group_name ASC, alias ASC"

        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute(query, params)
            return [Host.from_row(r) for r in cur.fetchall()]

    def update_last_connected(self, host_id: int):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._connection() as conn:
            conn.execute("UPDATE hosts SET last_connected_at = ? WHERE id = ?", (now, host_id))
            conn.commit()

    def toggle_favorite(self, host_id: int) -> bool:
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE hosts SET is_favorite = 1 - is_favorite WHERE id = ?", (host_id,))
            conn.commit()
            return cur.rowcount > 0

    # --- Group Operations ---

    def get_groups(self) -> List[str]:
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM groups ORDER BY sort_order ASC, name ASC")
            db_groups = [r["name"] for r in cur.fetchall()]
            # Also get any group names that exist in hosts table
            cur.execute("SELECT DISTINCT group_name FROM hosts WHERE group_name NOT IN (SELECT name FROM groups)")
            extra = [r["group_name"] for r in cur.fetchall() if r["group_name"]]
            return db_groups + extra

    def add_group(self, name: str, color: str = "#3b82f6") -> bool:
        name = name.strip()
        if not name:
            return False
        with self._connection() as conn:
            try:
                conn.execute("INSERT OR IGNORE INTO groups (name, color) VALUES (?, ?)", (name, color))
                conn.commit()
                return True
            except Exception:
                return False

    def delete_group(self, name: str, target_group: str = "Default") -> bool:
        name = name.strip()
        if name == "Default":
            return False
        with self._connection() as conn:
            # Reassign hosts to target group
            conn.execute("UPDATE hosts SET group_name = ? WHERE group_name = ?", (target_group, name))
            conn.execute("DELETE FROM groups WHERE name = ?", (name,))
            conn.commit()
            return True

    def rename_group(self, old_name: str, new_name: str) -> bool:
        """Rename a group and reassign all hosts belonging to it."""
        old_name = old_name.strip()
        new_name = new_name.strip()
        if not old_name or not new_name or old_name == new_name:
            return False
        if old_name == "Default":
            return False
        with self._connection() as conn:
            cur = conn.cursor()
            # Reject if target group name already exists in groups or hosts
            cur.execute("SELECT 1 FROM groups WHERE name = ?", (new_name,))
            if cur.fetchone():
                return False
            cur.execute("SELECT 1 FROM hosts WHERE group_name = ? LIMIT 1", (new_name,))
            if cur.fetchone():
                return False

            cur.execute("SELECT 1 FROM groups WHERE name = ?", (old_name,))
            if cur.fetchone():
                cur.execute("UPDATE groups SET name = ? WHERE name = ?", (new_name, old_name))
            else:
                cur.execute("INSERT OR IGNORE INTO groups (name) VALUES (?)", (new_name,))

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute("UPDATE hosts SET group_name = ?, updated_at = ? WHERE group_name = ?", (new_name, now, old_name))
            conn.commit()
            return True

    # --- Settings Operations ---

    def get_setting(self, key: str, default: str = "") -> str:
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cur.fetchone()
            if row:
                return row["value"]
            return default

    def set_setting(self, key: str, value: str):
        with self._connection() as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
            conn.commit()

    def get_all_settings(self) -> AppSettings:
        settings = AppSettings()
        # Look for default tvnviewer paths if setting not explicitly set
        default_viewer = settings.vnc_viewer_path
        if not os.path.exists(default_viewer):
            for path in [
                r"C:\Program Files\TightVNC\tvnviewer.exe",
                r"C:\Program Files (x86)\TightVNC\tvnviewer.exe",
                r"C:\Program Files\RealVNC\VNC Viewer\vncviewer.exe",
                r"C:\Program Files\TigerVNC\vncviewer.exe"
            ]:
                if os.path.exists(path):
                    default_viewer = path
                    break

        settings.vnc_viewer_path = self.get_setting("vnc_viewer_path", default_viewer)
        settings.embed_in_tab = self.get_setting("embed_in_tab", "1") == "1"
        settings.auto_refresh_interval = int(self.get_setting("auto_refresh_interval", "15"))
        settings.connection_timeout = int(self.get_setting("connection_timeout", "2"))
        settings.theme = self.get_setting("theme", "dark")
        settings.confirm_disconnect = self.get_setting("confirm_disconnect", "1") == "1"
        settings.screenshot_dir = self.get_setting("screenshot_dir", get_default_screenshots_dir())
        return settings

    def save_all_settings(self, settings: AppSettings):
        with self._connection() as conn:
            data = [
                ("vnc_viewer_path", settings.vnc_viewer_path),
                ("embed_in_tab", "1" if settings.embed_in_tab else "0"),
                ("auto_refresh_interval", str(settings.auto_refresh_interval)),
                ("connection_timeout", str(settings.connection_timeout)),
                ("theme", settings.theme),
                ("confirm_disconnect", "1" if settings.confirm_disconnect else "0"),
                ("screenshot_dir", settings.screenshot_dir),
            ]
            conn.executemany("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", data)
            conn.commit()
