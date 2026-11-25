"""Background Status Monitor for YutoVNC.

Monitors host availability (online/offline status) by testing TCP port 5900
and computing round-trip latency in milliseconds.
Uses concurrent worker threads to check multiple hosts simultaneously
without freezing the application GUI.
"""

import socket
import time
import threading
from typing import Dict, List, Optional, Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from yutovnc.models import Host, HostStatus

class StatusMonitor:
    def __init__(self, max_workers: int = 10):
        self.max_workers = max_workers
        self.statuses: Dict[int, HostStatus] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="VncProbe")
        self._callbacks: List[Callable[[int, HostStatus], None]] = []
        self._stop_event = threading.Event()
        self._poll_thread: Optional[threading.Thread] = None
        self._hosts_getter: Optional[Callable[[], List[Host]]] = None
        self.poll_interval = 15  # seconds

    def register_callback(self, cb: Callable[[int, HostStatus], None]):
        """Register a callback invoked when a host status is updated."""
        with self._lock:
            self._callbacks.append(cb)

    def unregister_callback(self, cb: Callable[[int, HostStatus], None]):
        with self._lock:
            if cb in self._callbacks:
                self._callbacks.remove(cb)

    def _notify(self, host_id: int, status: HostStatus):
        with self._lock:
            self.statuses[host_id] = status
            callbacks = list(self._callbacks)
        for cb in callbacks:
            try:
                cb(host_id, status)
            except Exception:
                pass

    def check_host_sync(self, host: Host, timeout: float = 1.5) -> HostStatus:
        """Probe a single host synchronously."""
        now_str = datetime.now().strftime("%H:%M:%S")
        status = HostStatus(host_id=host.id, last_checked=now_str)

        ip = (host.ip or "").strip()
        port = host.port or 5900

        if not ip:
            status.online = False
            status.error_message = "No IP provided"
            return status

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        start_time = time.perf_counter()
        try:
            res = s.connect_ex((ip, port))
            latency = (time.perf_counter() - start_time) * 1000.0
            if res == 0:
                status.online = True
                status.latency_ms = round(latency, 1)
                status.error_message = ""
            elif res in (10061, 111):  # WSAECONNREFUSED / ECONNREFUSED
                status.online = False
                status.error_message = f"Port {port} closed (refused)"
            elif res in (10060, 110):  # WSAETIMEDOUT / ETIMEDOUT
                status.online = False
                status.error_message = "Connection timed out"
            elif res == 10013:  # WSAEACCES
                status.online = False
                status.error_message = "Network access restricted (WSAEACCES)"
            else:
                status.online = False
                status.error_message = f"Error code {res}"
        except socket.timeout:
            status.online = False
            status.error_message = "Timed out"
        except socket.gaierror:
            status.online = False
            status.error_message = "Host not found (DNS error)"
        except Exception as e:
            status.online = False
            status.error_message = str(e)
        finally:
            try:
                s.close()
            except Exception:
                pass

        return status

    def check_host_async(self, host: Host, timeout: float = 1.5):
        """Submit a background probe for a single host."""
        def task():
            st = self.check_host_sync(host, timeout=timeout)
            self._notify(host.id, st)

        self._executor.submit(task)

    def check_all_hosts_async(self, hosts: List[Host], timeout: float = 1.5):
        """Submit background probes for a list of hosts."""
        for h in hosts:
            self.check_host_async(h, timeout=timeout)

    def get_status(self, host_id: int) -> Optional[HostStatus]:
        with self._lock:
            return self.statuses.get(host_id)

    def start_polling(self, hosts_getter: Callable[[], List[Host]], interval_seconds: int = 15):
        """Start recurring background monitoring."""
        self.stop_polling()
        self.poll_interval = max(5, interval_seconds)
        self._hosts_getter = hosts_getter
        self._stop_event.clear()

        def worker():
            while not self._stop_event.is_set():
                try:
                    if self._hosts_getter:
                        hosts = self._hosts_getter()
                        for h in hosts:
                            if self._stop_event.is_set():
                                break
                            self.check_host_async(h)
                except Exception:
                    pass
                self._stop_event.wait(self.poll_interval)

        self._poll_thread = threading.Thread(target=worker, daemon=True, name="VncPoller")
        self._poll_thread.start()

    def stop_polling(self):
        self._stop_event.set()
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=1.0)
        self._poll_thread = None

    def shutdown(self):
        self.stop_polling()
        self._executor.shutdown(wait=False)
