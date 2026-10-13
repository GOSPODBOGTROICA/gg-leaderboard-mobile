import pytest
from app.crypto import (
    evp_bytes_to_key,
    derive_password_from_ms,
    decrypt_cryptojs,
    encrypt_cryptojs,
)

def test_evp_bytes_to_key_lengths():
    password = b"test_password"
    salt = b"12345678"
    key, iv = evp_bytes_to_key(password, salt, key_len=32, iv_len=16)
    assert len(key) == 32
    assert len(iv) == 16
    assert isinstance(key, bytes)
    assert isinstance(iv, bytes)

def test_derive_password_from_ms():
    # Example: 1791854026082 -> 1a132d29d62
    ms = "1791854026082"
    pwd = derive_password_from_ms(ms)
    assert pwd == "1a132d29d62"
    assert derive_password_from_ms(1791854026082) == "1a132d29d62"

def test_derive_password_from_ms_invalid():
    with pytest.raises(ValueError):
        derive_password_from_ms(None)
    with pytest.raises(ValueError):
        derive_password_from_ms("")
    with pytest.raises(ValueError):
        derive_password_from_ms("invalid_number")

def test_aes_cbc_roundtrip():
    plain = '{"status": "ok", "rankings": [{"rank": 1, "nickname": "Hero", "points": 1250.5}]}'
    pwd = "my_secret_password_123"
    encrypted = encrypt_cryptojs(plain, pwd)
    assert encrypted.startswith("U2FsdGVkX1")  # Base64 encoding of b'Salted__'
    decrypted = decrypt_cryptojs(encrypted, pwd)
    assert decrypted == plain

def test_decrypt_missing_salted_header():
    # Valid base64 but does not start with Salted__
    bad_payload = "bm90X3NhbHRlZF9oZWFkZXJfZGF0YQ=="
    with pytest.raises(ValueError, match="Payload missing Salted__ header"):
        decrypt_cryptojs(bad_payload, "pwd")

def test_decrypt_corrupted_ciphertext_or_wrong_password():
    plain = '{"data": "secret"}'
    encrypted = encrypt_cryptojs(plain, "correct_password")
    with pytest.raises(ValueError):
        decrypt_cryptojs(encrypted, "wrong_password")
