"""Unit tests for YutoVNC exporter module."""

import unittest
import os
import tempfile
from yutovnc.database import Database
from yutovnc.models import Host
from yutovnc.exporter import DataExporter
from yutovnc.security import encrypt_password_dpapi

class TestExporter(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.db = Database(self.db_path)
        self.temp_files = []

    def tearDown(self):
        for f in self.temp_files:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass
        for ext in ["", "-wal", "-shm"]:
            f = self.db_path + ext
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass

    def test_json_export_import(self):
        h = Host(
            alias="Lab PC 05",
            ip="192.168.10.5",
            port=5900,
            group="Lab Komputer",
            password_enc=encrypt_password_dpapi("secret123"),
            notes="Testing JSON"
        )
        self.db.add_host(h)

        fd, json_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        self.temp_files.append(json_path)

        # Export
        count = DataExporter.export_to_json(self.db, json_path, master_password="MasterKey2026!")
        self.assertEqual(count, 1)

        # Import into fresh database
        fd2, db2_path = tempfile.mkstemp(suffix=".db")
        os.close(fd2)
        self.temp_files.extend([db2_path, db2_path + "-wal", db2_path + "-shm"])
        db2 = Database(db2_path)

        imported, skipped = DataExporter.import_from_json(db2, json_path, master_password="MasterKey2026!")
        self.assertEqual(imported, 1)
        self.assertEqual(skipped, 0)

        imported_hosts = db2.get_all_hosts()
        self.assertEqual(len(imported_hosts), 1)
        self.assertEqual(imported_hosts[0].alias, "Lab PC 05")
        self.assertEqual(imported_hosts[0].ip, "192.168.10.5")

    def test_csv_export_import(self):
        h = Host(
            alias="Kasir Depan",
            ip="10.0.0.15",
            port=5901,
            group="Kasir",
            notes="POS 1"
        )
        self.db.add_host(h)

        fd, csv_path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        self.temp_files.append(csv_path)

        count = DataExporter.export_to_csv(self.db, csv_path)
        self.assertEqual(count, 1)

        fd2, db2_path = tempfile.mkstemp(suffix=".db")
        os.close(fd2)
        self.temp_files.extend([db2_path, db2_path + "-wal", db2_path + "-shm"])
        db2 = Database(db2_path)

        imported, skipped = DataExporter.import_from_csv(db2, csv_path, default_password="pass")
        self.assertEqual(imported, 1)
        self.assertEqual(skipped, 0)
        self.assertEqual(len(db2.get_all_hosts()), 1)

    def test_vnc_file_import(self):
        fd, vnc_path = tempfile.mkstemp(suffix=".vnc")
        os.close(fd)
        self.temp_files.append(vnc_path)

        content = "[Connection]\nHost=192.168.1.99\nPort=5900\nViewOnly=0\n"
        with open(vnc_path, "w") as f:
            f.write(content)

        host = DataExporter.import_from_vnc_file(self.db, vnc_path)
        self.assertIsNotNone(host)
        self.assertEqual(host.ip, "192.168.1.99")
        self.assertEqual(host.port, 5900)

if __name__ == "__main__":
    unittest.main()
