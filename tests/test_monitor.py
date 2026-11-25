"""Unit tests for YutoVNC status monitor module."""

import unittest
import socket
import threading
from yutovnc.models import Host
from yutovnc.monitor import StatusMonitor

class TestMonitor(unittest.TestCase):
    def setUp(self):
        self.monitor = StatusMonitor(max_workers=2)

    def tearDown(self):
        self.monitor.shutdown()

    from unittest.mock import patch

    @patch("socket.socket")
    def test_online_host_mock(self, mock_socket_cls):
        mock_sock = mock_socket_cls.return_value
        mock_sock.connect_ex.return_value = 0

        host = Host(alias="MockOnline", ip="192.168.1.10", port=5900)
        status = self.monitor.check_host_sync(host, timeout=1.0)

        self.assertTrue(status.online)
        self.assertEqual(status.error_message, "")
        mock_sock.connect_ex.assert_called_once_with(("192.168.1.10", 5900))

    @patch("socket.socket")
    def test_offline_host_refused(self, mock_socket_cls):
        mock_sock = mock_socket_cls.return_value
        mock_sock.connect_ex.return_value = 10061

        host = Host(alias="MockOffline", ip="192.168.1.10", port=5900)
        status = self.monitor.check_host_sync(host, timeout=1.0)

        self.assertFalse(status.online)
        self.assertIn("closed", status.error_message)

if __name__ == "__main__":
    unittest.main()
