import asyncio
import base64
import time
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
import pytest
from fastapi.testclient import TestClient

from app.crypto import (
    evp_bytes_to_key,
    derive_password_from_ms,
    decrypt_cryptojs,
    encrypt_cryptojs,
)
from app.gg_client import GGClient, SUPPORTED_STAKES
from app.main import app
from app.config import get_settings


# ==============================================================================
# CATEGORY 1: Malformed & Corrupted Ciphertext Stress Tests
# ==============================================================================

class TestMalformedCiphertextAdversarial:
    """Stress tests for app.crypto with malformed, truncated, and corrupted payloads."""

    def test_empty_and_whitespace_payload(self):
        with pytest.raises(ValueError, match="Empty encrypted payload"):
            decrypt_cryptojs("", "password")
        with pytest.raises(ValueError):
            decrypt_cryptojs("   ", "password")

    @pytest.mark.parametrize("truncated_bytes", [
        b"",
        b"Salted",
        b"Salted__",              # exactly 8 bytes (missing salt)
        b"Salted__1234567",       # 15 bytes (< 16 bytes)
    ])
    def test_truncated_header_payloads(self, truncated_bytes):
        b64_payload = base64.b64encode(truncated_bytes).decode("ascii")
        with pytest.raises(ValueError):
            decrypt_cryptojs(b64_payload, "password")

    def test_exact_16_bytes_missing_ciphertext(self):
        # 8 bytes header + 8 bytes salt, but 0 bytes of ciphertext
        raw = b"Salted__12345678"
        b64_payload = base64.b64encode(raw).decode("ascii")
        with pytest.raises(ValueError, match="Decryption or unpadding failed"):
            decrypt_cryptojs(b64_payload, "password")

    @pytest.mark.parametrize("extra_len", [1, 5, 7, 15, 17, 31])
    def test_non_block_aligned_ciphertext(self, extra_len):
        # AES block size is 16 bytes. Any ciphertext not multiple of 16 must fail unpadding/block check.
        raw = b"Salted__12345678" + (b"X" * extra_len)
        b64_payload = base64.b64encode(raw).decode("ascii")
        with pytest.raises(ValueError, match="multiple of the block length|Decryption or unpadding failed"):
            decrypt_cryptojs(b64_payload, "password")

    @pytest.mark.parametrize("bad_header", [
        b"NotSalted_123456",
        b"salted__12345678",       # lowercase
        b"SALTED__12345678",       # uppercase
        b"Salted_ 12345678",       # space
        b"\x00\x00\x00\x00\x00\x00\x00\x0012345678",
    ])
    def test_missing_or_corrupted_salted_header(self, bad_header):
        raw = bad_header + b"\x00" * 16
        b64_payload = base64.b64encode(raw).decode("ascii")
        with pytest.raises(ValueError, match="Payload missing Salted__ header"):
            decrypt_cryptojs(b64_payload, "password")

    def test_invalid_base64_strings(self):
        bad_b64_strings = [
            "!!!not_base64!!!",
            "U2FsdGVkX1@@@@@@",
            "U2FsdGVkX1",  # incomplete base64 quantum
        ]
        for s in bad_b64_strings:
            with pytest.raises(ValueError):
                decrypt_cryptojs(s, "password")

    def test_corrupted_pkcs7_padding_via_bitflip(self):
        original = '{"valid": "json_data_payload_for_testing"}'
        pwd = "test_adversarial_password"
        encrypted = encrypt_cryptojs(original, pwd)
        raw = bytearray(base64.b64decode(encrypted))

        # Bitflip last byte (affects padding unpadder)
        raw[-1] ^= 0x01
        corrupted_b64 = base64.b64encode(raw).decode("ascii")

        with pytest.raises(ValueError, match="Decryption or unpadding failed"):
            decrypt_cryptojs(corrupted_b64, pwd)

    def test_bitflip_in_ciphertext_blocks(self):
        original = '{"status": "ok", "items": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]}'
        pwd = "test_block_corruption"
        encrypted = encrypt_cryptojs(original, pwd)
        raw = bytearray(base64.b64decode(encrypted))

        # Bitflip in the first ciphertext block (offset 16-32)
        raw[20] ^= 0xFF
        corrupted_b64 = base64.b64encode(raw).decode("ascii")

        with pytest.raises(ValueError):
            decrypt_cryptojs(corrupted_b64, pwd)

    def test_invalid_utf8_plaintext_after_unpadding(self):
        # Construct ciphertext that unpads to invalid UTF-8 bytes (e.g. b'\xff\xfe\x00\x00')
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding

        salt = b"12345678"
        pwd = "utf8_break_test"
        key, iv = evp_bytes_to_key(pwd, salt, 32, 16)

        # Non-UTF8 payload with valid PKCS7 padding
        invalid_utf8 = b"\xff\xfe\x80\xbf"
        padder = padding.PKCS7(128).padder()
        padded = padder.update(invalid_utf8) + padder.finalize()

        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        encryptor = cipher.encryptor()
        ct = encryptor.update(padded) + encryptor.finalize()

        b64_payload = base64.b64encode(b"Salted__" + salt + ct).decode("ascii")

        with pytest.raises(ValueError, match="Decryption or unpadding failed"):
            decrypt_cryptojs(b64_payload, pwd)


# ==============================================================================
# CATEGORY 2: Password & Milliseconds Header Derivation Tests
# ==============================================================================

class TestPasswordAndMsDerivationAdversarial:
    """Stress tests for password derivation and incorrect password rejection."""

    @pytest.mark.parametrize("ms_val, expected_pwd", [
        ("1791854742499", "1a132dd8be3"),
        (1791854742499, "1a132dd8be3"),
        ("1791854742499.0", "1a132dd8be3"),
        ("1791854742499.999", "1a132dd8be3"),
        ("1000", "3e8"),
        (1000, "3e8"),
        (0, "0"),
        ("0", "0"),
    ])
    def test_valid_and_boundary_ms_derivations(self, ms_val, expected_pwd):
        assert derive_password_from_ms(ms_val) == expected_pwd

    @pytest.mark.parametrize("bad_ms", [
        None,
        "",
        "   ",
        "abc",
        "123a",
        "nan",
        "null",
        "{}",
        "[]",
    ])
    def test_invalid_ms_values_raise_value_error(self, bad_ms):
        with pytest.raises(ValueError):
            derive_password_from_ms(bad_ms)

    def test_overflow_ms_values(self):
        with pytest.raises((ValueError, OverflowError)):
            derive_password_from_ms("inf")
        with pytest.raises((ValueError, OverflowError)):
            derive_password_from_ms("-inf")

    def test_decrypt_with_incorrect_passwords(self):
        original = '{"secret": "poker_telemetry_rankings"}'
        correct_pwd = "1a132dd8be3"
        encrypted = encrypt_cryptojs(original, correct_pwd)

        bad_passwords = [
            "1a132dd8be4",            # off-by-one ms
            "1a132dd8be2",            # off-by-one ms
            "1A132DD8BE3",            # case difference
            "1a132dd8be3 ",           # trailing space
            "password",
            "",
            "0",
        ]
        for bad_pwd in bad_passwords:
            with pytest.raises(ValueError):
                decrypt_cryptojs(encrypted, bad_pwd)


# ==============================================================================
# CATEGORY 3: In-Memory 15s TTL Caching & Concurrency Stress Tests
# ==============================================================================

class TestConcurrencyAndCachingAdversarial:
    """Empirical verification of 15s TTL caching and concurrency protection."""

    @pytest.fixture
    def mock_promo_data(self):
        return (
            1458,
            "Daily $50,000 Leaderboard (Spin&Gold)",
            {
                "$1": {
                    "stake": "$1",
                    "promotion_id": 230919,
                    "name": "Daily $50,000 Leaderboard (Spin&Gold) - $1",
                    "group_id": 1458,
                    "total_prize": 5000.0,
                    "prize_pool": "$5,000",
                    "status": "RUNNING",
                    "started_at": "2026-10-13T00:00:00Z",
                    "finished_at": "2026-10-13T08:00:00Z",
                },
                "$5": {
                    "stake": "$5",
                    "promotion_id": 230920,
                    "name": "Daily $50,000 Leaderboard (Spin&Gold) - $5",
                    "group_id": 1458,
                    "total_prize": 10000.0,
                    "prize_pool": "$10,000",
                    "status": "RUNNING",
                    "started_at": "2026-10-13T00:00:00Z",
                    "finished_at": "2026-10-13T08:00:00Z",
                }
            }
        )

    @pytest.fixture
    def mock_players(self):
        return [
            {"rank": 1, "nickname": "Leader1", "point": "1500.0", "prize": {"value": 100, "prizeItem": [{"type": "TICKET", "quantity": 1, "value": 100}]}},
            {"rank": 2, "nickname": "Chaser2", "point": "1200.0", "prize": {"value": 50, "prizeItem": [{"type": "TICKET", "quantity": 1, "value": 50}]}},
        ]

    @pytest.mark.anyio
    async def test_simultaneous_concurrent_requests_same_stake_thundering_herd(self, mock_promo_data, mock_players):
        """
        Adversarial test: Fire 25 concurrent requests for stake $1 simultaneously.
        Verify that exactly 1 upstream fetch occurs and 24 requests reuse the cache.
        """
        client = GGClient(default_group_id=1458, rank_ttl=15.0, group_ttl=60.0)

        # Pre-seed active promotions to isolate rank fetch concurrency
        client._promo_cache = (time.time(), mock_promo_data[0], mock_promo_data[1], mock_promo_data[2])

        fetch_counter = 0

        async def slow_upstream_fetch(httpx_client, url):
            nonlocal fetch_counter
            fetch_counter += 1
            await asyncio.sleep(0.05)  # Simulate 50ms network delay
            return mock_players

        with patch.object(client, "_fetch_decrypted", side_effect=slow_upstream_fetch):
            tasks = [
                client.get_leaderboard(stake="$1", hero_query="Leader1")
                for _ in range(25)
            ]
            results = await asyncio.gather(*tasks)

        # Verify exactly 1 network request fired
        assert fetch_counter == 1, f"Expected 1 upstream fetch, got {fetch_counter} (thundering herd failure!)"

        # Verify all 25 tasks received identical, valid results
        assert len(results) == 25
        for res in results:
            assert res.stake == "$1"
            assert res.promotion_id == 230919
            assert len(res.players) == 2
            assert res.hero.rank == 1

        # Verify that subsequent requests return cached=True
        cached_flags = [r.cached for r in results]
        assert cached_flags.count(True) >= 24

    @pytest.mark.anyio
    async def test_concurrent_requests_for_different_stakes(self, mock_promo_data, mock_players):
        """
        Adversarial test: 10 concurrent requests for $1 and 10 concurrent requests for $5.
        Verify per-stake locking: exactly 1 fetch for $1 and 1 fetch for $5.
        """
        client = GGClient(default_group_id=1458, rank_ttl=15.0, group_ttl=60.0)
        client._promo_cache = (time.time(), mock_promo_data[0], mock_promo_data[1], mock_promo_data[2])

        stake_calls = {"$1": 0, "$5": 0}

        async def mock_fetch(httpx_client, url):
            await asyncio.sleep(0.03)
            if "230919" in url:
                stake_calls["$1"] += 1
            elif "230920" in url:
                stake_calls["$5"] += 1
            return mock_players

        with patch.object(client, "_fetch_decrypted", side_effect=mock_fetch):
            tasks = []
            for _ in range(10):
                tasks.append(client.get_leaderboard(stake="$1"))
                tasks.append(client.get_leaderboard(stake="$5"))
            results = await asyncio.gather(*tasks)

        assert stake_calls["$1"] == 1
        assert stake_calls["$5"] == 1
        assert len(results) == 20

    @pytest.mark.anyio
    async def test_cache_ttl_expiration_and_refresh(self, mock_promo_data, mock_players):
        """
        Verify that requests within TTL reuse cache, and requests after TTL refresh cache.
        """
        # Set a short TTL of 0.1s for test speed
        client = GGClient(default_group_id=1458, rank_ttl=0.1, group_ttl=60.0)
        client._promo_cache = (time.time(), mock_promo_data[0], mock_promo_data[1], mock_promo_data[2])

        fetch_count = 0

        async def count_fetch(httpx_client, url):
            nonlocal fetch_count
            fetch_count += 1
            return mock_players

        with patch.object(client, "_fetch_decrypted", side_effect=count_fetch):
            # Call 1: cold cache -> fetch 1
            r1 = await client.get_leaderboard(stake="$1")
            assert fetch_count == 1
            assert r1.cached is False

            # Call 2: within TTL (0.01s) -> fetch 1 (reused)
            r2 = await client.get_leaderboard(stake="$1")
            assert fetch_count == 1
            assert r2.cached is True

            # Wait for TTL to expire
            await asyncio.sleep(0.12)

            # Call 3: after TTL -> fetch 2
            r3 = await client.get_leaderboard(stake="$1")
            assert fetch_count == 2
            assert r3.cached is False

    @pytest.mark.anyio
    async def test_group_discovery_concurrency(self, mock_players):
        """
        Verify that 15 concurrent calls to get_active_promotions make only 1 group probe.
        """
        client = GGClient(default_group_id=1458, rank_ttl=15.0, group_ttl=60.0)

        group_probe_count = 0

        async def mock_fetch_group(httpx_client, url):
            nonlocal group_probe_count
            group_probe_count += 1
            await asyncio.sleep(0.04)
            return {
                "name": "Daily $50,000 Leaderboard (Spin&Gold)",
                "promotions": [
                    {
                        "promotionId": 230919,
                        "promotion": {
                            "name": "Daily $50,000 Leaderboard (Spin&Gold) - $1",
                            "status": "RUNNING",
                            "totalPrizeValue": 5000.0
                        }
                    }
                ]
            }

        with patch.object(client, "_fetch_decrypted", side_effect=mock_fetch_group):
            tasks = [client.get_active_promotions() for _ in range(15)]
            results = await asyncio.gather(*tasks)

        assert group_probe_count == 1, f"Expected 1 group probe, got {group_probe_count}"
        assert len(results) == 15


# ==============================================================================
# CATEGORY 4: Network Timeouts & Upstream 502/503 Fault Injection Tests
# ==============================================================================

class TestNetworkFaultInjectionAdversarial:
    """Stress tests for upstream failures: timeouts, 502/503 status, and stale cache fallback."""

    @pytest.fixture
    def mock_promo_data(self):
        return (
            1458,
            "Daily $50,000 Leaderboard (Spin&Gold)",
            {
                "$1": {
                    "stake": "$1",
                    "promotion_id": 230919,
                    "name": "Daily $50,000 Leaderboard (Spin&Gold) - $1",
                    "group_id": 1458,
                    "total_prize": 5000.0,
                    "prize_pool": "$5,000",
                    "status": "RUNNING",
                }
            }
        )

    @pytest.mark.anyio
    async def test_cold_cache_upstream_502_error_raises_runtime_error(self, mock_promo_data):
        client = GGClient(default_group_id=1458)
        client._promo_cache = (time.time(), mock_promo_data[0], mock_promo_data[1], mock_promo_data[2])

        async def fail_502(httpx_client, url):
            raise RuntimeError("GGPoker API returned status 502 for https://pml.good-game-service.com/lapi/leaderboard/230919")

        with patch.object(client, "_fetch_decrypted", side_effect=fail_502):
            with pytest.raises(RuntimeError, match="status 502"):
                await client.get_leaderboard(stake="$1")

    @pytest.mark.anyio
    async def test_cold_cache_upstream_timeout_raises_runtime_error(self, mock_promo_data):
        client = GGClient(default_group_id=1458)
        client._promo_cache = (time.time(), mock_promo_data[0], mock_promo_data[1], mock_promo_data[2])

        async def fail_timeout(httpx_client, url):
            raise httpx.ReadTimeout("Connection timed out after 12.0s")

        with patch.object(client, "_fetch_decrypted", side_effect=fail_timeout):
            with pytest.raises(RuntimeError, match="timed out"):
                await client.get_leaderboard(stake="$1")

    @pytest.mark.anyio
    async def test_warm_cache_graceful_fallback_on_upstream_502(self, mock_promo_data):
        """
        Adversarial resilience test:
        1. Cache is populated successfully.
        2. TTL expires.
        3. Upstream returns 502 Bad Gateway.
        4. GGClient MUST fall back to stale cache rather than failing!
        """
        client = GGClient(default_group_id=1458, rank_ttl=0.05)
        client._promo_cache = (time.time(), mock_promo_data[0], mock_promo_data[1], mock_promo_data[2])

        # Step 1: Initial successful fetch
        mock_players = [{"rank": 1, "nickname": "HeroPlayer", "point": "500.0"}]
        with patch.object(client, "_fetch_decrypted", AsyncMock(return_value=mock_players)):
            res1 = await client.get_leaderboard(stake="$1")
            assert res1.players[0].nickname == "HeroPlayer"

        # Step 2: Let TTL expire
        await asyncio.sleep(0.06)

        # Step 3: Upstream crashes with 502 Bad Gateway
        async def upstream_502(httpx_client, url):
            raise RuntimeError("GGPoker API returned status 502 Bad Gateway")

        with patch.object(client, "_fetch_decrypted", side_effect=upstream_502):
            # Step 4: Call must NOT crash; must return stale cached response
            res2 = await client.get_leaderboard(stake="$1")
            assert res2.cached is True
            assert res2.players[0].nickname == "HeroPlayer"

    @pytest.mark.anyio
    async def test_warm_cache_graceful_fallback_on_upstream_timeout(self, mock_promo_data):
        """
        Adversarial resilience test: Stale cache fallback on upstream ReadTimeout.
        """
        client = GGClient(default_group_id=1458, rank_ttl=0.05)
        client._promo_cache = (time.time(), mock_promo_data[0], mock_promo_data[1], mock_promo_data[2])

        mock_players = [{"rank": 1, "nickname": "ResilientUser", "point": "999.0"}]
        with patch.object(client, "_fetch_decrypted", AsyncMock(return_value=mock_players)):
            await client.get_leaderboard(stake="$1")

        await asyncio.sleep(0.06)

        async def upstream_timeout(httpx_client, url):
            raise httpx.ReadTimeout("Gateway timeout connecting to upstream")

        with patch.object(client, "_fetch_decrypted", side_effect=upstream_timeout):
            res = await client.get_leaderboard(stake="$1")
            assert res.cached is True
            assert res.players[0].nickname == "ResilientUser"

    def test_fastapi_endpoint_502_mapping_on_cold_failure(self):
        """
        Verify FastAPI /api/leaderboard maps cold upstream failures to HTTP 502 Bad Gateway.
        """
        test_client = TestClient(app)
        pin = get_settings().pin
        auth_res = test_client.post("/api/auth", json={"pin": pin})
        token = auth_res.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Clear global client cache to simulate cold failure
        from app.gg_client import get_gg_client
        gg = get_gg_client()
        gg._rank_cache.clear()
        gg._promo_cache = (0.0, 1458, "", {})

        with patch.object(gg, "_fetch_decrypted", side_effect=RuntimeError("GGPoker API returned status 502")):
            res = test_client.get("/api/leaderboard?stake=$1", headers=headers)
            assert res.status_code == 502
            assert "Upstream GGPoker leaderboard error" in res.json()["detail"]
