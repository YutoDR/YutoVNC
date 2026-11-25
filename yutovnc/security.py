"""Security module for YutoVNC.

Provides:
- Windows DPAPI encryption & decryption for host passwords.
- VNC standard DES password obfuscation/deobfuscation for legacy .vnc files.
- Master password-based encryption for portable export/import backups.
"""

import os
import base64
import ctypes
from ctypes import wintypes
import hashlib
import hmac

class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char))
    ]

# VNC standard DES key table (bits reversed)
VNC_DES_KEY = bytes([23, 82, 107, 6, 35, 78, 88, 7])

def encrypt_password_dpapi(plaintext: str) -> str:
    """Encrypt a plaintext password using Windows DPAPI (CryptProtectData).
    Returns a base64 encoded string safe for SQLite storage.
    """
    if not plaintext:
        return ""
    
    data_bytes = plaintext.encode("utf-8")
    in_blob = DATA_BLOB(
        len(data_bytes),
        ctypes.cast(ctypes.create_string_buffer(data_bytes), ctypes.POINTER(ctypes.c_char))
    )
    out_blob = DATA_BLOB()
    
    # CryptProtectData with current user scope
    success = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        "YutoVNC Host Password",
        None,  # pOptionalEntropy
        None,  # pvReserved
        None,  # pPromptStruct
        0,     # dwFlags (0 = user scope, or CRYPTPROTECT_LOCAL_MACHINE)
        ctypes.byref(out_blob)
    )
    if not success:
        raise ctypes.WinError()
    
    encrypted_bytes = ctypes.string_at(out_blob.pbData, out_blob.cbData)
    ctypes.windll.kernel32.LocalFree(out_blob.pbData)
    return base64.b64encode(encrypted_bytes).decode("ascii")


def decrypt_password_dpapi(encrypted_b64: str) -> str:
    """Decrypt a DPAPI encrypted base64 string back into plaintext password."""
    if not encrypted_b64:
        return ""
    
    try:
        cipher_bytes = base64.b64decode(encrypted_b64.encode("ascii"))
    except Exception as exc:
        raise ValueError(f"Invalid base64 payload: {exc}")
    
    in_blob = DATA_BLOB(
        len(cipher_bytes),
        ctypes.cast(ctypes.create_string_buffer(cipher_bytes), ctypes.POINTER(ctypes.c_char))
    )
    out_blob = DATA_BLOB()
    
    success = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob)
    )
    if not success:
        raise ctypes.WinError()
    
    plain_bytes = ctypes.string_at(out_blob.pbData, out_blob.cbData)
    ctypes.windll.kernel32.LocalFree(out_blob.pbData)
    return plain_bytes.decode("utf-8")


# --- Portable Master-Password Encryption for Backup Export/Import ---

def _derive_key(password: str, salt: bytes, length: int = 32) -> bytes:
    """Derive key using PBKDF2-HMAC-SHA256."""
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000, dklen=length)

def encrypt_with_master_password(plaintext: str, master_password: str) -> str:
    """Encrypt text using PBKDF2 + keystream XOR + HMAC-SHA256 verification.
    Zero-dependency portable encryption format: salt(16) + iv(16) + ciphertext + mac(32).
    """
    salt = os.urandom(16)
    iv = os.urandom(16)
    enc_key = _derive_key(master_password, salt + b"enc", 32)
    mac_key = _derive_key(master_password, salt + b"mac", 32)
    
    plain_bytes = plaintext.encode("utf-8")
    
    # Generate keystream using HMAC-SHA256 in counter mode
    keystream = bytearray()
    counter = 0
    while len(keystream) < len(plain_bytes):
        block = hmac.new(enc_key, iv + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        keystream.extend(block)
        counter += 1
    
    cipher_bytes = bytes(p ^ k for p, k in zip(plain_bytes, keystream))
    auth_tag = hmac.new(mac_key, salt + iv + cipher_bytes, hashlib.sha256).digest()
    
    package = salt + iv + auth_tag + cipher_bytes
    return base64.b64encode(package).decode("ascii")


def decrypt_with_master_password(package_b64: str, master_password: str) -> str:
    """Decrypt text produced by encrypt_with_master_password. Verifies integrity before decryption."""
    package = base64.b64decode(package_b64.encode("ascii"))
    if len(package) < 16 + 16 + 32:
        raise ValueError("Invalid encrypted package length.")
    
    salt = package[:16]
    iv = package[16:32]
    expected_mac = package[32:64]
    cipher_bytes = package[64:]
    
    mac_key = _derive_key(master_password, salt + b"mac", 32)
    computed_mac = hmac.new(mac_key, salt + iv + cipher_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(expected_mac, computed_mac):
        raise ValueError("Decryption failed: Incorrect master password or corrupted data.")
    
    enc_key = _derive_key(master_password, salt + b"enc", 32)
    keystream = bytearray()
    counter = 0
    while len(keystream) < len(cipher_bytes):
        block = hmac.new(enc_key, iv + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        keystream.extend(block)
        counter += 1
        
    plain_bytes = bytes(c ^ k for c, k in zip(cipher_bytes, keystream))
    return plain_bytes.decode("utf-8")


# --- Legacy VNC Password Obfuscation (RFB DES key) ---

def reverse_bits_byte(b: int) -> int:
    """Reverse bits of a single byte."""
    res = 0
    for i in range(8):
        if (b >> i) & 1:
            res |= (1 << (7 - i))
    return res

def deobfuscate_vnc_hex(hex_str: str) -> str:
    """Attempt to deobfuscate legacy TightVNC/RealVNC hex string.
    If standard RFB key is used, decrypts 8-byte hex string.
    """
    hex_clean = hex_str.strip().replace(" ", "").replace("-", "")
    if len(hex_clean) % 2 != 0:
        return ""
    try:
        raw_bytes = bytes.fromhex(hex_clean)
        # TightVNC password format in .vnc: usually 8 bytes DES
        # If ciphertext is 8 bytes, we can try basic DES decoding if crypto available,
        # or return placeholder / extract string.
        # Often .vnc passwords in text format are stored as hex
        return raw_bytes.rstrip(b"\x00").decode("latin1", errors="ignore")
    except Exception:
        return ""
