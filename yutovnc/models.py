"""Data models for YutoVNC."""

from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any
from datetime import datetime

@dataclass
class Host:
    id: Optional[int] = None
    alias: str = ""
    ip: str = ""
    port: int = 5900
    group: str = "Default"
    password_enc: str = ""          # DPAPI encrypted base64 string
    view_only: bool = False
    fullscreen: bool = False
    scaling: str = "auto"           # "auto", "fit", "100%", "none"
    notes: str = ""
    is_favorite: bool = False
    sort_order: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    last_connected_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row) -> "Host":
        """Construct Host from SQLite sqlite3.Row object."""
        return cls(
            id=row["id"],
            alias=row["alias"],
            ip=row["ip"],
            port=row["port"],
            group=row["group_name"],
            password_enc=row["password_enc"] or "",
            view_only=bool(row["view_only"]),
            fullscreen=bool(row["fullscreen"]),
            scaling=row["scaling"] or "auto",
            notes=row["notes"] or "",
            is_favorite=bool(row["is_favorite"]),
            sort_order=row["sort_order"] or 0,
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
            last_connected_at=row["last_connected_at"]
        )

@dataclass
class HostStatus:
    host_id: int
    online: bool = False
    latency_ms: float = 0.0
    last_checked: str = ""
    error_message: str = ""

from yutovnc.paths import get_default_screenshots_dir

@dataclass
class AppSettings:
    vnc_viewer_path: str = r"C:\Program Files\TightVNC\tvnviewer.exe"
    embed_in_tab: bool = True
    auto_refresh_interval: int = 15      # In seconds, 0 = disabled
    connection_timeout: int = 2          # In seconds
    theme: str = "dark"                  # "dark" or "light"
    confirm_disconnect: bool = True
    custom_cad_shortcut: str = "Ctrl+Alt+Del"
    screenshot_dir: str = field(default_factory=get_default_screenshots_dir)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
