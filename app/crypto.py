import base64
import hashlib
import os
from typing import Tuple, Union
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding

def evp_bytes_to_key(password: Union[bytes, str], salt: Union[bytes, str], key_len: int = 32, iv_len: int = 16) -> Tuple[bytes, bytes]:
    """
    OpenSSL EVP_BytesToKey algorithm using MD5 (1 iteration), matching CryptoJS format.
    Generates key_len bytes of key (default 32 bytes for AES-256) and iv_len bytes of IV (default 16 bytes).
    """
    if isinstance(password, str):
        password = password.encode('utf-8')
    if isinstance(salt, str):
        salt = salt.encode('utf-8')
        
    d = b''
    d_i = b''
    target_len = key_len + iv_len
    while len(d) < target_len:
        d_i = hashlib.md5(d_i + password + salt).digest()
        d += d_i
    return d[:key_len], d[key_len:target_len]

def derive_password_from_ms(ms_val: Union[str, int, float]) -> str:
    """
    Derives the decryption password from the HTTP 'milliseconds' response header.
    Formula: hex(int(ms))[2:]
    """
    if ms_val is None:
        raise ValueError("Missing milliseconds header")
    s = str(ms_val).strip()
    if not s:
        raise ValueError("Empty milliseconds header")
    try:
        ms_int = int(float(s))
    except ValueError as e:
        raise ValueError(f"Invalid milliseconds header format: {ms_val}") from e
    return hex(ms_int)[2:]

def decrypt_cryptojs(encrypted_b64: str, password_str: str) -> str:
    """
    Decrypts an AES-256-CBC ciphertext formatted in standard CryptoJS / OpenSSL format.
    The payload begins with b'Salted__' (8 bytes), followed by 8 bytes salt, followed by ciphertext.
    """
    if not encrypted_b64:
        raise ValueError("Empty encrypted payload")
    try:
        raw = base64.b64decode(encrypted_b64)
    except Exception as e:
        raise ValueError(f"Base64 decode failure: {e}") from e

    if len(raw) < 16 or raw[:8] != b'Salted__':
        raise ValueError("Payload missing Salted__ header")

    salt = raw[8:16]
    ciphertext = raw[16:]
    password = password_str.encode('utf-8')
    key, iv = evp_bytes_to_key(password, salt, 32, 16)

    try:
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        padded_plain = decryptor.update(ciphertext) + decryptor.finalize()

        unpadder = padding.PKCS7(128).unpadder()
        plain = unpadder.update(padded_plain) + unpadder.finalize()
        return plain.decode('utf-8')
    except Exception as e:
        raise ValueError(f"Decryption or unpadding failed: {e}") from e

def encrypt_cryptojs(plaintext: str, password_str: str) -> str:
    """
    Encrypts a string using AES-256-CBC in CryptoJS / OpenSSL compatible format.
    Useful for local testing, fixtures, and roundtrip verification.
    """
    salt = os.urandom(8)
    password = password_str.encode('utf-8')
    key, iv = evp_bytes_to_key(password, salt, 32, 16)

    padder = padding.PKCS7(128).padder()
    padded_bytes = padder.update(plaintext.encode('utf-8')) + padder.finalize()

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded_bytes) + encryptor.finalize()

    assembled = b'Salted__' + salt + ciphertext
    return base64.b64encode(assembled).decode('ascii')
