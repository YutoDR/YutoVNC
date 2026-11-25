"""Network and VNC Scanner Module for YutoVNC.

Features:
- Fast multi-threaded TCP port scanning (ThreadPoolExecutor).
- Automatic local network interface and subnet detection (CIDR / IP range).
- Reverse DNS / hostname resolution for discovered devices.
- Non-blocking asynchronous scanning with progress tracking and cancellation.
"""

import socket
import time
import ipaddress
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Optional, Callable, Tuple

@dataclass
class ScanResult:
    ip: str
    port: int = 5900
    is_open: bool = False
    hostname: str = ""
    latency_ms: float = 0.0
    error_message: str = ""

class NetworkScanner:
    def __init__(self, max_workers: int = 64):
        self.max_workers = max_workers
        self._stop_event = threading.Event()
        self._executor: Optional[ThreadPoolExecutor] = None
        self._running = False

    @staticmethod
    def get_local_ip() -> str:
        """Detect the primary active local IPv4 address."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Does not transmit packets; probes system routing table
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = "192.168.1.1"
        finally:
            s.close()
        return ip

    @classmethod
    def get_default_subnet(cls) -> Tuple[str, str, str]:
        """Detect local subnet.
        Returns (cidr_string, start_ip, end_ip).
        Example: ('192.168.1.0/24', '192.168.1.1', '192.168.1.254')
        """
        local_ip = cls.get_local_ip()
        parts = local_ip.split(".")
        if len(parts) == 4 and not local_ip.startswith("127."):
            prefix = f"{parts[0]}.{parts[1]}.{parts[2]}"
            return f"{prefix}.0/24", f"{prefix}.1", f"{prefix}.254"
        return "192.168.1.0/24", "192.168.1.1", "192.168.1.254"

    @staticmethod
    def parse_target_ips(
        cidr_or_range: str = "",
        start_ip: str = "",
        end_ip: str = ""
    ) -> List[str]:
        """Generate a list of IPv4 strings from CIDR, range, or start/end inputs.
        Supports:
        - '192.168.1.0/24'
        - '192.168.1.10 - 192.168.1.50'
        - start_ip='192.168.1.1', end_ip='192.168.1.100'
        - single IP: '192.168.1.50'
        """
        cidr_or_range = (cidr_or_range or "").strip()
        start_ip = (start_ip or "").strip()
        end_ip = (end_ip or "").strip()

        # Case 1: Start and End IP specified separately
        if start_ip and end_ip:
            try:
                s_int = int(ipaddress.IPv4Address(start_ip))
                e_int = int(ipaddress.IPv4Address(end_ip))
                if s_int > e_int:
                    s_int, e_int = e_int, s_int
                # Limit range to max 1024 IPs for safety
                if e_int - s_int > 1024:
                    e_int = s_int + 1024
                return [str(ipaddress.IPv4Address(i)) for i in range(s_int, e_int + 1)]
            except Exception:
                pass

        # Case 2: Range in string separated by '-'
        if "-" in cidr_or_range:
            parts = [p.strip() for p in cidr_or_range.split("-", 1)]
            if len(parts) == 2:
                try:
                    s_int = int(ipaddress.IPv4Address(parts[0]))
                    e_int = int(ipaddress.IPv4Address(parts[1]))
                    if s_int > e_int:
                        s_int, e_int = e_int, s_int
                    if e_int - s_int > 1024:
                        e_int = s_int + 1024
                    return [str(ipaddress.IPv4Address(i)) for i in range(s_int, e_int + 1)]
                except Exception:
                    pass

        # Case 3: CIDR notation (e.g. 192.168.1.0/24)
        if "/" in cidr_or_range:
            try:
                net = ipaddress.ip_network(cidr_or_range, strict=False)
                # Cap at /22 (1024 hosts) to prevent excessive memory/time
                hosts = list(net.hosts())
                if len(hosts) > 1024:
                    hosts = hosts[:1024]
                return [str(h) for h in hosts]
            except Exception:
                pass

        # Case 4: Single IP
        if cidr_or_range:
            try:
                ip_obj = ipaddress.IPv4Address(cidr_or_range)
                return [str(ip_obj)]
            except Exception:
                pass

        # Fallback default
        _, def_start, def_end = NetworkScanner.get_default_subnet()
        return NetworkScanner.parse_target_ips(start_ip=def_start, end_ip=def_end)

    @staticmethod
    def resolve_hostname(ip: str) -> str:
        """Resolve IP address to host/computer name."""
        try:
            return socket.gethostbyaddr(ip)[0]
        except Exception:
            return ""

    def scan_host(self, ip: str, port: int = 5900, timeout: float = 0.4) -> ScanResult:
        """Scan a single host IP on the given port."""
        if self._stop_event.is_set():
            return ScanResult(ip=ip, port=port, is_open=False)

        res = ScanResult(ip=ip, port=port)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)

        t0 = time.perf_counter()
        try:
            code = s.connect_ex((ip, port))
            latency = (time.perf_counter() - t0) * 1000.0
            if code == 0:
                res.is_open = True
                res.latency_ms = round(latency, 1)
                # Attempt hostname resolution for open VNC servers
                res.hostname = self.resolve_hostname(ip)
            else:
                res.is_open = False
        except socket.timeout:
            res.is_open = False
            res.error_message = "Timed out"
        except Exception as e:
            res.is_open = False
            res.error_message = str(e)
        finally:
            try:
                s.close()
            except Exception:
                pass

        return res

    def scan_network_async(
        self,
        ips: List[str],
        port: int = 5900,
        timeout: float = 0.4,
        on_result: Optional[Callable[[ScanResult], None]] = None,
        on_progress: Optional[Callable[[int, int], None]] = None,
        on_complete: Optional[Callable[[List[ScanResult]], None]] = None
    ):
        """Asynchronously scan a list of IP addresses in a background thread."""
        self.stop()
        self._stop_event.clear()
        self._running = True

        def worker():
            total = len(ips)
            scanned = 0
            results: List[ScanResult] = []

            self._executor = ThreadPoolExecutor(
                max_workers=self.max_workers,
                thread_name_prefix="VncScanWorker"
            )

            # Submit all scan tasks
            future_to_ip = {
                self._executor.submit(self.scan_host, ip, port, timeout): ip
                for ip in ips
            }

            for future in as_completed(future_to_ip):
                if self._stop_event.is_set():
                    break
                try:
                    res = future.result()
                    results.append(res)
                    scanned += 1
                    if on_result:
                        on_result(res)
                    if on_progress:
                        on_progress(scanned, total)
                except Exception:
                    scanned += 1
                    if on_progress:
                        on_progress(scanned, total)

            self._running = False
            if on_complete:
                on_complete(results)

        threading.Thread(target=worker, daemon=True, name="VncScanManager").start()

    def stop(self):
        """Stop/cancel ongoing scan."""
        self._stop_event.set()
        if self._executor:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running
