"""Unit tests for YutoVNC database module."""

import unittest
import os
import tempfile
from yutovnc.database import Database
from yutovnc.models import Host
from yutovnc.security import encrypt_password_dpapi

class TestDatabase(unittest.TestCase):
    def setUp(self):
        fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.db = Database(self.temp_db_path)

    def tearDown(self):
        import time, gc
        gc.collect()
        for _ in range(5):
            try:
                if os.path.exists(self.temp_db_path):
                    os.remove(self.temp_db_path)
                # also remove WAL/SHM files
                for ext in ["-wal", "-shm"]:
                    f = self.temp_db_path + ext
                    if os.path.exists(f):
                        os.remove(f)
                break
            except PermissionError:
                time.sleep(0.05)

    def test_crud_operations(self):
        # 1. Add host
        enc_pw = encrypt_password_dpapi("serverpass")
        host1 = Host(
            alias="Server Kasir 01",
            ip="192.168.1.50",
            port=5900,
            group="Kasir / POS",
            password_enc=enc_pw,
            notes="PC Kasir Utama"
        )
        h_id = self.db.add_host(host1)
        self.assertIsNotNone(h_id)
        self.assertGreater(h_id, 0)

        # 2. Get by ID
        fetched = self.db.get_host_by_id(h_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.alias, "Server Kasir 01")
        self.assertEqual(fetched.ip, "192.168.1.50")
        self.assertEqual(fetched.group, "Kasir / POS")

        # 3. Update host
        fetched.alias = "Server Kasir 01 (Updated)"
        fetched.is_favorite = True
        self.assertTrue(self.db.update_host(fetched))
        updated = self.db.get_host_by_id(h_id)
        self.assertEqual(updated.alias, "Server Kasir 01 (Updated)")
        self.assertTrue(updated.is_favorite)

        # 4. Search and filter
        results = self.db.get_all_hosts(search_query="Kasir")
        self.assertEqual(len(results), 1)

        results_group = self.db.get_all_hosts(group_filter="Kasir / POS")
        self.assertEqual(len(results_group), 1)

        # 5. Delete host
        self.assertTrue(self.db.delete_host(h_id))
        self.assertIsNone(self.db.get_host_by_id(h_id))

    def test_group_management(self):
        self.db.add_group("Lab Jaringan")
        groups = self.db.get_groups()
        self.assertIn("Lab Jaringan", groups)

        # Add a host in 'Lab Jaringan' and rename group
        h = Host(alias="PC-01", ip="192.168.1.10", group="Lab Jaringan")
        h_id = self.db.add_host(h)

        self.assertTrue(self.db.rename_group("Lab Jaringan", "Lab Komputer 2"))
        groups_after = self.db.get_groups()
        self.assertNotIn("Lab Jaringan", groups_after)
        self.assertIn("Lab Komputer 2", groups_after)

        fetched = self.db.get_host_by_id(h_id)
        self.assertEqual(fetched.group, "Lab Komputer 2")

        # Cannot rename Default or rename to an existing group
        self.assertFalse(self.db.rename_group("Default", "CustomDefault"))
        self.assertFalse(self.db.rename_group("Lab Komputer 2", "Default"))

    def test_settings_persistence(self):
        settings = self.db.get_all_settings()
        settings.auto_refresh_interval = 45
        settings.theme = "light"
        self.db.save_all_settings(settings)

        reloaded = self.db.get_all_settings()
        self.assertEqual(reloaded.auto_refresh_interval, 45)
        self.assertEqual(reloaded.theme, "light")

if __name__ == "__main__":
    unittest.main()
