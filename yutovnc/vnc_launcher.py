"""VNC Launcher and Session Manager for YutoVNC.

Handles:
- Auto-detecting VNC viewers (TightVNC, UltraVNC, TigerVNC)
- One-click launch with auto-login credential injection
- Win32 window embedding (docking remote session into tabbed UI)
- Active session management & graceful termination
- Quick toolbar actions: Ctrl+Alt+Del, Screenshot capture, View-Only, Scaling
"""

import os
import time
import subprocess
import threading
import ctypes
from ctypes import wintypes
import struct
from typing import Optional, List, Dict, Callable
from datetime import datetime
from yutovnc.models import Host, AppSettings
from yutovnc.security import decrypt_password_dpapi
from yutovnc.paths import get_resource_path

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

# Win32 Constants
GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_TABSTOP = 0x00010000
WS_CLIPCHILDREN = 0x02000000
WS_CLIPSIBLINGS = 0x04000000
WS_POPUP = 0x80000000
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_EX_APPWINDOW = 0x00040000

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040

WM_COMMAND = 0x0111
WM_SYSCOMMAND = 0x0112
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
VK_CONTROL = 0x11
VK_MENU = 0x12       # ALT key
VK_DELETE = 0x2E

# TightVNC Viewer Toolbar / System Menu Command IDs
TIGHTVNC_CMD_SEND_CAD = 206
TIGHTVNC_CMD_SCALE_100 = 213
TIGHTVNC_CMD_SCALE_AUTO = 214
TIGHTVNC_CMD_FULLSCREEN = 215
TB_ISBUTTONCHECKED = 0x040A


def normalize_scaling_mode(scaling: Optional[str]) -> str:
    """Normalize stored host scaling preference into 'fit' or '100%'."""
    val = str(scaling or "").strip().lower()
    if val in ("100%", "100"):
        return "100%"
    return "fit"

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

class Session:
    """Represents an active VNC connection session."""
    def __init__(self, host: Host, proc: Optional[subprocess.Popen], is_embedded: bool = False):
        self.session_id = f"{host.id}_{int(time.time()*1000)}"
        self.host = host
        self.proc = proc
        self.is_embedded = is_embedded
        self.hwnd: Optional[int] = None
        self.container_hwnd: Optional[int] = None
        self.attached_threads: Optional[tuple] = None
        self._closed: bool = False
        self.start_time = datetime.now()
        self.is_view_only = host.view_only
        # Scale to Fit is enabled by default unless host explicitly specifies "100%"
        self.is_scaled = (normalize_scaling_mode(host.scaling) == "fit")

    def is_alive(self) -> bool:
        if self._closed or self.proc is None:
            return False
        return self.proc.poll() is None

    def detach_thread_input(self):
        """Detach any attached Win32 thread input queues."""
        if self.attached_threads:
            wnd_tid, parent_tid = self.attached_threads
            self.attached_threads = None
            try:
                if wnd_tid and parent_tid and wnd_tid != parent_tid:
                    user32.AttachThreadInput(wnd_tid, parent_tid, False)
            except Exception:
                pass
        if self.hwnd:
            detach_embedded_window(self.hwnd, self.container_hwnd)

    def terminate(self):
        """Forcefully stop the VNC process and release window/thread handles."""
        self._closed = True
        self.detach_thread_input()
        proc = self.proc
        self.proc = None
        self.hwnd = None
        if proc is not None:
            try:
                if proc.poll() is None:
                    proc.terminate()
                    for _ in range(10):
                        if proc.poll() is not None:
                            break
                        time.sleep(0.05)
                    if proc.poll() is None:
                        proc.kill()
                        proc.wait(timeout=1.0)
            except Exception:
                pass


def find_viewer_path(configured_path: Optional[str] = None) -> str:
    """Find a valid VNC viewer executable."""
    if configured_path and os.path.exists(configured_path):
        return configured_path

    # 1. Check bundled binaries (via sys._MEIPASS or adjacent to exe)
    for bundled in [
        get_resource_path(os.path.join("bin", "tvnviewer.exe")),
        get_resource_path("tvnviewer.exe"),
        get_resource_path(os.path.join("bin", "vncviewer.exe")),
        get_resource_path("vncviewer.exe"),
    ]:
        if os.path.exists(bundled):
            return bundled

    # 2. Common standard system installations
    standard_paths = [
        r"C:\Program Files\TightVNC\tvnviewer.exe",
        r"C:\Program Files (x86)\TightVNC\tvnviewer.exe",
        r"C:\Program Files\TigerVNC\vncviewer.exe",
        r"C:\Program Files (x86)\TigerVNC\vncviewer.exe",
        r"C:\Program Files\UltraVNC\vncviewer.exe",
        r"C:\Program Files (x86)\UltraVNC\vncviewer.exe",
        r"C:\Program Files\RealVNC\VNC Viewer\vncviewer.exe"
    ]
    for p in standard_paths:
        if os.path.exists(p):
            return p

    # 3. Check PATH
    for name in ["tvnviewer.exe", "vncviewer.exe"]:
        where = subprocess.run(["where", name], capture_output=True, text=True, shell=True)
        if where.returncode == 0 and where.stdout.strip():
            first = where.stdout.strip().splitlines()[0]
            if os.path.exists(first):
                return first

    return configured_path or r"C:\Program Files\TightVNC\tvnviewer.exe"


def build_viewer_command(viewer_path: str, host: Host, password_plain: str) -> List[str]:
    """Construct command line arguments for the VNC viewer."""
    exe_name = os.path.basename(viewer_path).lower()
    cmd = [viewer_path]

    if "tvnviewer" in exe_name:
        # TightVNC Viewer switches
        cmd.append(f"-host={host.ip}")
        cmd.append(f"-port={host.port}")
        if password_plain:
            cmd.append(f"-password={password_plain}")
        cmd.append("-viewonly=yes" if host.view_only else "-viewonly=no")
        cmd.append("-fullscreen=yes" if host.fullscreen else "-fullscreen=no")
        # Default Scale to Fit (-scale=auto) unless host explicitly set "100%"
        cmd.append("-scale=100" if normalize_scaling_mode(host.scaling) == "100%" else "-scale=auto")
    elif "tiger" in exe_name:
        # TigerVNC
        if password_plain:
            cmd.extend(["-Password", password_plain])
        if host.view_only:
            cmd.append("-ViewOnly")
        if host.fullscreen:
            cmd.append("-FullScreen")
        cmd.append(f"{host.ip}:{host.port}")
    else:
        # UltraVNC / Generic RFB
        cmd.extend(["-connect", f"{host.ip}::{host.port}"])
        if password_plain:
            cmd.extend(["-password", password_plain])
        if host.view_only:
            cmd.append("-viewonly")
        if host.fullscreen:
            cmd.append("-fullscreen")

    return cmd


def find_window_by_pid(pid: int, timeout_seconds: float = 30.0) -> Optional[int]:
    """Wait for and locate the session window handle (HWND) belonging to process ID.
    Prioritizes 'session' class windows (TightVNC session) and top-level viewer windows.
    """
    start = time.time()
    while time.time() - start < timeout_seconds:
        session_hwnds: List[int] = []
        fallback_hwnds: List[int] = []

        def enum_window_callback(hwnd: int, lparam: int) -> bool:
            proc_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc_id))
            if proc_id.value == pid:
                cls_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, cls_buf, 256)
                cls_name = cls_buf.value.lower()

                # Ignore IME, helper, or notify icon windows
                if cls_name in ("msctfime ui", "ime", "notifyiconwindowclass"):
                    return True

                if "session" in cls_name or "vncviewer" in cls_name:
                    session_hwnds.append(hwnd)
                elif cls_name != "#32770":  # Avoid premature dialog docking
                    fallback_hwnds.append(hwnd)
            return True

        cb = WNDENUMPROC(enum_window_callback)
        user32.EnumWindows(cb, 0)

        if session_hwnds:
            return session_hwnds[0]
        if fallback_hwnds and (time.time() - start > 1.5):
            return fallback_hwnds[0]

        time.sleep(0.1)

    return None


def embed_window_into_parent(child_hwnd: int, parent_hwnd: int, width: int, height: int) -> Optional[tuple]:
    """Reparent a Win32 window into a parent container frame, attach UI thread input, and adjust styles."""
    if not child_hwnd or not parent_hwnd:
        return None

    # 1. Attach VNC window thread input to the UI parent window thread input
    # so cross-process SetFocus and keyboard input routing work properly.
    wnd_thread = user32.GetWindowThreadProcessId(child_hwnd, None)
    parent_thread = user32.GetWindowThreadProcessId(parent_hwnd, None)
    attached = None
    if wnd_thread and parent_thread and wnd_thread != parent_thread:
        user32.AttachThreadInput(wnd_thread, parent_thread, True)
        attached = (wnd_thread, parent_thread)

    # 2. Set parent
    user32.SetParent(child_hwnd, parent_hwnd)

    # 3. Modify style: child window with tabstop, remove thick borders, caption, and popups
    old_style = user32.GetWindowLongW(child_hwnd, GWL_STYLE)
    new_style = (old_style | WS_CHILD | WS_VISIBLE | WS_TABSTOP | WS_CLIPCHILDREN | WS_CLIPSIBLINGS) & ~(
        WS_POPUP | WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX
    )
    user32.SetWindowLongW(child_hwnd, GWL_STYLE, new_style)

    # 4. Remove WS_EX_APPWINDOW from extended style so taskbar does not show a duplicate icon
    old_ex = user32.GetWindowLongW(child_hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(child_hwnd, GWL_EXSTYLE, old_ex & ~WS_EX_APPWINDOW)

    # 5. Position and size to fit parent frame
    w = max(100, width)
    h = max(100, height)
    user32.MoveWindow(child_hwnd, 0, 0, w, h, True)
    user32.SetWindowPos(
        child_hwnd,
        0,
        0, 0,
        w, h,
        SWP_NOZORDER | SWP_FRAMECHANGED | SWP_SHOWWINDOW
    )
    return attached


def find_inner_viewer_hwnd(session_hwnd: int) -> int:
    """Locate the inner TightVNC 'Viewer' canvas child window if present."""
    if not session_hwnd or not user32.IsWindow(session_hwnd):
        return session_hwnd

    found: List[int] = []

    def enum_child(ch: int, _lp: int) -> bool:
        cls_buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(ch, cls_buf, 256)
        title_buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(ch, title_buf, 256)
        if "session" in cls_buf.value.lower() or title_buf.value == "Viewer":
            found.append(ch)
            return False
        return True

    user32.EnumChildWindows(session_hwnd, WNDENUMPROC(enum_child), 0)
    return found[0] if found else session_hwnd


def detach_embedded_window(child_hwnd: Optional[int], parent_hwnd: Optional[int] = None):
    """Detach Win32 thread input queues between an embedded VNC window and the UI thread."""
    if not child_hwnd or not user32.IsWindow(child_hwnd):
        return

    wnd_thread = user32.GetWindowThreadProcessId(child_hwnd, None)
    cur_thread = kernel32.GetCurrentThreadId()
    parent_thread = (
        user32.GetWindowThreadProcessId(parent_hwnd, None)
        if parent_hwnd and user32.IsWindow(parent_hwnd)
        else cur_thread
    )

    if wnd_thread and parent_thread and wnd_thread != parent_thread:
        user32.AttachThreadInput(wnd_thread, parent_thread, False)
    if wnd_thread and cur_thread and wnd_thread != cur_thread and cur_thread != parent_thread:
        user32.AttachThreadInput(wnd_thread, cur_thread, False)


def focus_embedded_window(child_hwnd: Optional[int], parent_hwnd: Optional[int] = None) -> Optional[tuple]:
    """Ensure thread input is attached and set Win32 keyboard focus onto the embedded VNC canvas."""
    if not child_hwnd or not user32.IsWindow(child_hwnd):
        return None

    wnd_thread = user32.GetWindowThreadProcessId(child_hwnd, None)
    cur_thread = kernel32.GetCurrentThreadId()
    parent_thread = user32.GetWindowThreadProcessId(parent_hwnd, None) if parent_hwnd else cur_thread

    attached = None
    if wnd_thread and parent_thread and wnd_thread != parent_thread:
        user32.AttachThreadInput(wnd_thread, parent_thread, True)
        attached = (wnd_thread, parent_thread)
    if wnd_thread and cur_thread and wnd_thread != cur_thread and cur_thread != parent_thread:
        user32.AttachThreadInput(wnd_thread, cur_thread, True)

    target = find_inner_viewer_hwnd(child_hwnd)
    user32.SetFocus(child_hwnd)
    if target and target != child_hwnd and user32.IsWindow(target):
        user32.SetFocus(target)
    return attached


def find_toolbar_hwnd(session_hwnd: Optional[int]) -> Optional[int]:
    """Locate the TightVNC Viewer ToolbarWindow32 child window if present."""
    if not session_hwnd or not user32.IsWindow(session_hwnd):
        return None

    found: List[int] = []

    def enum_child(ch: int, _lp: int) -> bool:
        cls_buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(ch, cls_buf, 256)
        if "toolbar" in cls_buf.value.lower():
            found.append(ch)
            return False
        return True

    user32.EnumChildWindows(session_hwnd, WNDENUMPROC(enum_child), 0)
    return found[0] if found else None


def is_window_auto_scaled(hwnd: Optional[int]) -> Optional[bool]:
    """Return True if TightVNC Auto-Scale button is checked, False if unchecked, None if unknown."""
    tb_hwnd = find_toolbar_hwnd(hwnd)
    if not tb_hwnd:
        return None
    return bool(user32.SendMessageW(tb_hwnd, TB_ISBUTTONCHECKED, TIGHTVNC_CMD_SCALE_AUTO, 0))


def set_window_scaling(hwnd: Optional[int], fit: bool, force_if_unknown: bool = False) -> bool:
    """Switch TightVNC Viewer scaling between Scale: Auto (Fit) and Scale: 100% (Original).

    TightVNC's WM_COMMAND 214 (Scale: Auto) acts as a toggle, so when `fit=True` we check
    the toolbar button state first and only post 214 when Auto-Scale is currently OFF.
    WM_COMMAND 213 (Scale: 100%) is idempotent.
    """
    if not hwnd or not user32.IsWindow(hwnd):
        return False

    current_fit = is_window_auto_scaled(hwnd)
    if fit:
        if current_fit is True:
            return True
        if current_fit is False or force_if_unknown:
            user32.PostMessageW(hwnd, WM_COMMAND, TIGHTVNC_CMD_SCALE_AUTO, 0)
        return True

    if current_fit is False:
        return True
    user32.PostMessageW(hwnd, WM_COMMAND, TIGHTVNC_CMD_SCALE_100, 0)
    return True


def resize_embedded_window(child_hwnd: int, width: int, height: int):
    """Resize embedded window to match parent container resize."""
    if child_hwnd and user32.IsWindow(child_hwnd):
        user32.MoveWindow(child_hwnd, 0, 0, max(10, width), max(10, height), True)


def capture_window_screenshot(hwnd: int, output_filepath: str) -> bool:
    """Capture window snapshot directly using Win32 GDI and save as standard BMP."""
    if not hwnd or not user32.IsWindow(hwnd):
        return False

    os.makedirs(os.path.dirname(os.path.abspath(output_filepath)), exist_ok=True)

    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    w = max(10, rect.right - rect.left)
    h = max(10, rect.bottom - rect.top)

    hdc_wnd = user32.GetDC(hwnd)
    if not hdc_wnd:
        return False

    hdc_mem = gdi32.CreateCompatibleDC(hdc_wnd)
    hbm = gdi32.CreateCompatibleBitmap(hdc_wnd, w, h)
    old_bm = gdi32.SelectObject(hdc_mem, hbm)

    # Try PrintWindow with full content, fallback to BitBlt
    PW_RENDERFULLCONTENT = 2
    res = user32.PrintWindow(hwnd, hdc_mem, PW_RENDERFULLCONTENT)
    if not res:
        gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_wnd, 0, 0, 0x00CC0020)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    bmi = BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.biWidth = w
    bmi.biHeight = -h  # top-down DIB
    bmi.biPlanes = 1
    bmi.biBitCount = 32
    bmi.biCompression = 0

    row_bytes = w * 4
    buf_size = row_bytes * h
    buf = (ctypes.c_char * buf_size)()

    gdi32.GetDIBits(hdc_mem, hbm, 0, h, buf, ctypes.byref(bmi), 0)

    # Build BMP file: 14 bytes header + 40 bytes DIB header + pixel data
    file_header = struct.pack("<2sIHHI", b"BM", 14 + 40 + buf_size, 0, 0, 14 + 40)
    bmi_bytes = ctypes.string_at(ctypes.byref(bmi), ctypes.sizeof(bmi))

    with open(output_filepath, "wb") as f:
        f.write(file_header)
        f.write(bmi_bytes)
        f.write(ctypes.string_at(buf, buf_size))

    # Clean up GDI handles
    gdi32.SelectObject(hdc_mem, old_bm)
    gdi32.DeleteObject(hbm)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(hwnd, hdc_wnd)

    return os.path.exists(output_filepath) and os.path.getsize(output_filepath) > 0


def send_cad_to_window(hwnd: int):
    """Send Ctrl+Alt+Del directly to the remote VNC session via TightVNC command."""
    if not hwnd or not user32.IsWindow(hwnd):
        return

    # TightVNC Viewer handles command 206 (Send Ctrl+Alt+Del) directly over RFB
    # without locking the local workstation.
    user32.PostMessageW(hwnd, WM_COMMAND, TIGHTVNC_CMD_SEND_CAD, 0)


class SessionManager:
    """Manages active VNC sessions across tabs and windows."""
    def __init__(self):
        self.sessions: Dict[str, Session] = {}

    def launch_host(
        self,
        host: Host,
        settings: AppSettings,
        container_hwnd: Optional[int] = None,
        container_width: int = 800,
        container_height: int = 600,
        on_embedded_ready: Optional[Callable[[Session], None]] = None,
        on_error: Optional[Callable[[str], None]] = None
    ) -> Session:
        """Launch 1-click connection with auto-login."""
        viewer_path = find_viewer_path(settings.vnc_viewer_path)
        if not os.path.exists(viewer_path):
            err = f"VNC Viewer not found at '{viewer_path}'. Please check Settings."
            if on_error:
                on_error(err)
            raise FileNotFoundError(err)

        # Decrypt password via DPAPI
        plain_password = ""
        if host.password_enc:
            try:
                plain_password = decrypt_password_dpapi(host.password_enc)
            except Exception as e:
                # If decryption fails (e.g. copied from another user profile), fallback to prompt/empty
                plain_password = ""

        cmd = build_viewer_command(viewer_path, host, plain_password)
        embed_mode = settings.embed_in_tab and (container_hwnd is not None)

        try:
            proc = subprocess.Popen(cmd)
        except Exception as e:
            err = f"Failed to start VNC viewer process: {e}"
            if on_error:
                on_error(err)
            raise

        session = Session(host, proc, is_embedded=embed_mode)
        session.container_hwnd = container_hwnd
        self.sessions[session.session_id] = session

        if embed_mode:
            # Asynchronously wait for window HWND and reparent
            def embed_worker():
                start = time.time()
                docked = False
                while time.time() - start < 30.0 and not session._closed and proc.poll() is None:
                    hwnd = find_window_by_pid(proc.pid, timeout_seconds=1.0)
                    if session._closed or proc.poll() is not None:
                        break
                    if hwnd and user32.IsWindow(hwnd):
                        session.hwnd = hwnd
                        rect = wintypes.RECT()
                        user32.GetClientRect(container_hwnd, ctypes.byref(rect))
                        cw = max(100, rect.right - rect.left) if (rect.right - rect.left) > 0 else container_width
                        ch = max(100, rect.bottom - rect.top) if (rect.bottom - rect.top) > 0 else container_height
                        session.attached_threads = embed_window_into_parent(hwnd, container_hwnd, cw, ch)
                        if session._closed:
                            session.terminate()
                            return
                        session.is_embedded = True
                        docked = True
                        if on_embedded_ready:
                            on_embedded_ready(session)
                        break
                    time.sleep(0.1)

                if not docked:
                    session.is_embedded = False

            t = threading.Thread(target=embed_worker, daemon=True)
            t.start()

        return session

    def close_session(self, session_id: str):
        if session_id in self.sessions:
            sess = self.sessions.pop(session_id)
            sess.terminate()

    def close_all(self):
        for sess in list(self.sessions.values()):
            sess.terminate()
        self.sessions.clear()

    def get_session(self, session_id: str) -> Optional[Session]:
        return self.sessions.get(session_id)
