"""Unit tests for YutoVNC network scanner module."""

import unittest
from unittest.mock import patch, MagicMock
from yutovnc.scanner import NetworkScanner, ScanResult

class TestNetworkScanner(unittest.TestCase):
    def setUp(self):
        self.scanner = NetworkScanner(max_workers=4)

    def tearDown(self):
        self.scanner.stop()

    def test_parse_cidr(self):
        ips = NetworkScanner.parse_target_ips("192.168.10.0/24")
        self.assertEqual(len(ips), 254)
        self.assertEqual(ips[0], "192.168.10.1")
        self.assertEqual(ips[-1], "192.168.10.254")

    def test_parse_range(self):
        ips = NetworkScanner.parse_target_ips("10.0.0.5 - 10.0.0.10")
        self.assertEqual(len(ips), 6)
        self.assertEqual(ips[0], "10.0.0.5")
        self.assertEqual(ips[-1], "10.0.0.10")

    def test_parse_start_end_args(self):
        ips = NetworkScanner.parse_target_ips(start_ip="172.16.0.1", end_ip="172.16.0.3")
        self.assertEqual(len(ips), 3)
        self.assertEqual(ips, ["172.16.0.1", "172.16.0.2", "172.16.0.3"])

    def test_parse_single_ip(self):
        ips = NetworkScanner.parse_target_ips("192.168.1.50")
        self.assertEqual(ips, ["192.168.1.50"])

    def test_get_default_subnet(self):
        cidr, s, e = NetworkScanner.get_default_subnet()
        self.assertTrue("/24" in cidr)
        self.assertTrue(s.endswith(".1"))
        self.assertTrue(e.endswith(".254"))

    @patch("socket.socket")
    def test_scan_host_open(self, mock_socket_cls):
        mock_sock = mock_socket_cls.return_value
        mock_sock.connect_ex.return_value = 0

        with patch.object(self.scanner, "resolve_hostname", return_value="PC-SERVER"):
            res = self.scanner.scan_host("192.168.1.50", port=5900, timeout=0.1)

        self.assertTrue(res.is_open)
        self.assertEqual(res.ip, "192.168.1.50")
        self.assertEqual(res.port, 5900)
        self.assertEqual(res.hostname, "PC-SERVER")
        self.assertGreaterEqual(res.latency_ms, 0.0)

    @patch("socket.socket")
    def test_scan_host_closed(self, mock_socket_cls):
        mock_sock = mock_socket_cls.return_value
        mock_sock.connect_ex.return_value = 10061

        res = self.scanner.scan_host("192.168.1.51", port=5900, timeout=0.1)
        self.assertFalse(res.is_open)
        self.assertEqual(res.ip, "192.168.1.51")

    def test_scanner_stop(self):
        self.scanner.stop()
        self.assertTrue(self.scanner._stop_event.is_set())
        self.assertFalse(self.scanner.is_running)

    def test_scanned_hosts_add_to_default_group(self):
        import tempfile, os
        from yutovnc.database import Database
        from yutovnc.models import Host

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            temp_db_path = f.name
        try:
            db = Database(temp_db_path)
            # Simulate adding host with group='Default' from scanner
            scanned_host = Host(
                alias="PC-LAB-01",
                ip="192.168.1.100",
                port=5900,
                group="Default",
                notes="Ditemukan via Pemindai Jaringan"
            )
            h_id = db.add_host(scanned_host)
            self.assertIsNotNone(h_id)

            saved = db.get_host_by_id(h_id)
            self.assertIsNotNone(saved)
            self.assertEqual(saved.alias, "PC-LAB-01")
            self.assertEqual(saved.group, "Default")

            # Check that it appears under group='Default'
            default_hosts = db.get_all_hosts(group_filter="Default")
            self.assertEqual(len(default_hosts), 1)
            self.assertEqual(default_hosts[0].ip, "192.168.1.100")
        finally:
            if os.path.exists(temp_db_path):
                os.remove(temp_db_path)

if __name__ == "__main__":
    unittest.main()
