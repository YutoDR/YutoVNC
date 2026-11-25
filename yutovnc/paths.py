"""Path resolution and environment management for YutoVNC.

Ensures:
- Safe database and config storage in %APPDATA%\\YutoVNC (avoids Program Files permission errors).
- Seamless asset and binary resolution in development and PyInstaller frozen executable modes (sys._MEIPASS).
- Portable mode detection and backward compatibility.
"""

import os
import sys
import shutil

def get_app_dir() -> str:
    """Return application directory (folder containing main executable or main script)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    # Dev mode: parent of 'yutovnc' package
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_resource_path(relative_path: str) -> str:
    """Get absolute path to resource, compatible with development and PyInstaller.
    
    Resolution order:
    1. sys._MEIPASS (PyInstaller unpacked assets folder)
    2. Adjacent to sys.executable (installed assets directory)
    3. Project root (development mode)
    """
    # 1. PyInstaller temporary folder
    if hasattr(sys, "_MEIPASS"):
        meipass_candidate = os.path.join(sys._MEIPASS, relative_path)
        if os.path.exists(meipass_candidate):
            return meipass_candidate

    # 2. Next to executable
    if getattr(sys, "frozen", False):
        exe_candidate = os.path.join(os.path.dirname(sys.executable), relative_path)
        if os.path.exists(exe_candidate):
            return exe_candidate

    # 3. Development root
    dev_candidate = os.path.join(get_app_dir(), relative_path)
    return dev_candidate


def get_app_data_dir() -> str:
    """Return user AppData directory: %APPDATA%\\YutoVNC.
    Guaranteed to be writable by standard non-admin users.
    Falls back gracefully if running in a restricted test/sandbox environment.
    """
    appdata = os.getenv("APPDATA")
    if not appdata:
        appdata = os.path.expanduser("~")
    target_dir = os.path.join(appdata, "YutoVNC")
    try:
        os.makedirs(target_dir, exist_ok=True)
        # Verify write permission
        test_file = os.path.join(target_dir, ".write_test")
        with open(test_file, "w") as f:
            f.write("ok")
        os.remove(test_file)
        return target_dir
    except (PermissionError, OSError):
        fallback_dir = os.path.join(get_app_dir(), ".appdata")
        os.makedirs(fallback_dir, exist_ok=True)
        return fallback_dir


def get_database_path() -> str:
    """Get path to SQLite database.
    Defaults to %APPDATA%\\YutoVNC\\yutovnc.db.
    If an existing database is found in app directory (portable mode migration),
    it is safely copied to AppData on first launch.
    """
    appdata_dir = get_app_data_dir()
    appdata_db = os.path.join(appdata_dir, "yutovnc.db")

    # If already exists in AppData, use it directly
    if os.path.exists(appdata_db):
        return appdata_db

    # Check for legacy/portable database in app directory
    portable_db = os.path.join(get_app_dir(), "yutovnc.db")
    if os.path.exists(portable_db):
        try:
            shutil.copy2(portable_db, appdata_db)
            for ext in ["-wal", "-shm"]:
                sidecar = portable_db + ext
                if os.path.exists(sidecar):
                    shutil.copy2(sidecar, appdata_db + ext)
        except Exception:
            pass

    return appdata_db


def get_default_screenshots_dir() -> str:
    """Return default directory for captured screenshots."""
    screenshots_dir = os.path.join(get_app_data_dir(), "screenshots")
    os.makedirs(screenshots_dir, exist_ok=True)
    return screenshots_dir


def get_logs_dir() -> str:
    """Return directory for application logs."""
    logs_dir = os.path.join(get_app_data_dir(), "logs")
    os.makedirs(logs_dir, exist_ok=True)
    return logs_dir
