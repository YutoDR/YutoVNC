"""Unit tests for YutoVNC security module."""

import unittest
from yutovnc.security import (
    encrypt_password_dpapi,
    decrypt_password_dpapi,
    encrypt_with_master_password,
    decrypt_with_master_password
)

class TestSecurity(unittest.TestCase):
    def test_dpapi_roundtrip(self):
        passwords = [
            "admin123",
            "P@$$w0rd!#%^&*()",
            "SangatRahasia!2026",
            "   spaces and tabs \t   ",
            "kata_sandi_vnc"
        ]
        for pwd in passwords:
            encrypted = encrypt_password_dpapi(pwd)
            self.assertNotEqual(pwd, encrypted)
            decrypted = decrypt_password_dpapi(encrypted)
            self.assertEqual(pwd, decrypted)

    def test_dpapi_empty(self):
        self.assertEqual(encrypt_password_dpapi(""), "")
        self.assertEqual(decrypt_password_dpapi(""), "")

    def test_master_password_backup(self):
        secret_data = '{"hosts": [{"alias": "Server IT", "password": "supersecret"}]}'
        master = "MasterKey2026!"
        pkg = encrypt_with_master_password(secret_data, master)
        self.assertNotEqual(secret_data, pkg)

        decrypted = decrypt_with_master_password(pkg, master)
        self.assertEqual(secret_data, decrypted)

        # Wrong password should fail
        with self.assertRaises(ValueError):
            decrypt_with_master_password(pkg, "WrongPassword")

if __name__ == "__main__":
    unittest.main()
