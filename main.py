"""YutoVNC - Smart Remote Client
Main application entry point.
"""

import sys
import os

# Ensure package root is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Enable High DPI awareness on Windows for crisp typography
try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        import ctypes
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

from yutovnc.database import Database
from yutovnc.models import Host
from yutovnc.security import encrypt_password_dpapi
from yutovnc.ui.main_window import MainWindow

def seed_demo_data_if_empty(db: Database):
    """Seed helpful sample hosts on first startup if database is brand new."""
    existing = db.get_all_hosts()
    if len(existing) == 0:
        demo_hosts = [
            Host(
                alias="Server IT Utama",
                ip="192.168.1.10",
                port=5900,
                group="Server IT",
                password_enc=encrypt_password_dpapi("admin123"),
                notes="Server DC & File Share lantai 2",
                is_favorite=True
            ),
            Host(
                alias="PC Lab Komputer 01",
                ip="192.168.10.101",
                port=5900,
                group="Lab Komputer",
                password_enc=encrypt_password_dpapi("labpass"),
                notes="PC Siswa Meja 1 Baris Depan",
                is_favorite=True
            ),
            Host(
                alias="PC Lab Komputer 02",
                ip="192.168.10.102",
                port=5900,
                group="Lab Komputer",
                password_enc=encrypt_password_dpapi("labpass"),
                notes="PC Siswa Meja 2",
                is_favorite=False
            ),
            Host(
                alias="Kasir Utama (POS 1)",
                ip="10.0.0.51",
                port=5900,
                group="Kasir / POS",
                password_enc=encrypt_password_dpapi("kasir123"),
                notes="Komputer Kasir Meja Depan",
                is_favorite=False
            ),
            Host(
                alias="PC Ruang Meeting",
                ip="192.168.1.88",
                port=5900,
                group="Default",
                password_enc=encrypt_password_dpapi("meeting2026"),
                notes="PC Presentasi Proyektor Ruang Rapat",
                is_favorite=False
            )
        ]
        for h in demo_hosts:
            db.add_host(h)

def main():
    db = Database()
    seed_demo_data_if_empty(db)

    app = MainWindow()
    app.mainloop()

if __name__ == "__main__":
    main()
