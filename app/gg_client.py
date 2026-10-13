import asyncio
import json
import re
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any

import httpx

from app.config import get_settings
from app.crypto import derive_password_from_ms, decrypt_cryptojs
from app.models import (
    StakesResponse,
    StakeItem,
    LeaderboardResponse,
    HeroTelemetry,
    PlayerEntry,
)
from app.telemetry import (
    compute_cutoff,
    build_player_entries,
    calculate_hero_telemetry,
)

SUPPORTED_STAKES = [
    "$0.25",
    "$1",
    "$3",
    "$5",
    "$10",
    "$20",
    "$50",
    "$100",
    "$200"
]

def normalize_stake_str(raw_stake: str) -> str:
    """Normalizes stake strings such as '1', '$1', '0.25', '$0.25' to '$1' format."""
    s = str(raw_stake).strip()
    if not s.startswith("$"):
        s = f"${s}"
    return s

class GGClient:
    """
    Async client for GGPoker Leaderboard API.
    Features:
    - Real-time AES-256-CBC decryption with dynamic header password derivation
    - Monthly group discovery starting at 1458 (fast cache)
    - Active daily Spin & Gold stakes extraction ($0.25 to $200)
    - Top-50 rankings retrieval with player, prize, and gap models
    - 15-second TTL in-memory caching with asyncio.Lock
    - Resilient fallback to cached data during upstream hiccups
    """
    BASE_URL = "https://pml.good-game-service.com/lapi/leaderboard"
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }

    def __init__(
        self,
        default_group_id: Optional[int] = None,
        rank_ttl: Optional[float] = None,
        group_ttl: Optional[float] = None,
    ):
        settings = get_settings()
        self.group_id = default_group_id or settings.default_group_id
        self.rank_ttl = rank_ttl if rank_ttl is not None else settings.rank_cache_ttl
        self.group_ttl = group_ttl if group_ttl is not None else settings.group_cache_ttl

        # In-memory caches
        # _promo_cache: (timestamp, group_id, group_name, dict[stake_str, dict])
        self._promo_cache: Tuple[float, int, str, Dict[str, Any]] = (0.0, self.group_id, "", {})

        # _rank_cache: stake_str -> {
        #   "timestamp": float,
        #   "promotion_id": int,
        #   "finished_at": Optional[str],
        #   "raw_players": List[dict]
        # }
        self._rank_cache: Dict[str, Dict[str, Any]] = {}

        self._rank_locks: Dict[str, asyncio.Lock] = {}
        self._group_lock = asyncio.Lock()

    def _get_stake_lock(self, stake: str) -> asyncio.Lock:
        if stake not in self._rank_locks:
            self._rank_locks[stake] = asyncio.Lock()
        return self._rank_locks[stake]

    def _extract_stake(self, promo_name: str) -> Optional[str]:
        # Filter out "Daily $50,000 Leaderboard" prefix to prevent matching false '$50'
        clean = re.sub(r'^Daily\s+\$[0-9,]+\s+Leaderboard', '', promo_name, flags=re.IGNORECASE).strip()
        m = re.search(r'\$([0-9]+(?:\.[0-9]+)?)\s*\)?$', clean)
        if m:
            return f"${m.group(1)}"
        return None

    async def _fetch_decrypted(self, client: httpx.AsyncClient, url: str) -> Any:
        res = await client.get(url, timeout=12.0)
        if res.status_code != 200:
            raise RuntimeError(f"GGPoker API returned status {res.status_code} for {url}")
        
        ms = res.headers.get("milliseconds")
        if not ms:
            raise ValueError(f"Missing milliseconds header in response from {url}")
        
        pwd = derive_password_from_ms(ms)
        data_json = res.json()
        encrypted_data = data_json.get("data")
        if not encrypted_data:
            raise ValueError(f"Missing 'data' field in JSON response from {url}")

        decrypted_str = decrypt_cryptojs(encrypted_data, pwd)
        return json.loads(decrypted_str)

    def _is_group_active(self, group_data: Dict[str, Any], now_utc: datetime) -> bool:
        for p_item in group_data.get("promotions", []):
            promo = p_item.get("promotion", {})
            s_str = promo.get("startedAt")
            f_str = promo.get("finishedAt")
            if s_str and f_str:
                try:
                    s_dt = datetime.fromisoformat(s_str)
                    f_dt = datetime.fromisoformat(f_str)
                    if s_dt <= now_utc <= f_dt:
                        return True
                except Exception:
                    pass
            if promo.get("status") == "RUNNING":
                return True
        return False

    async def _find_active_group(self, client: httpx.AsyncClient) -> Tuple[int, Dict[str, Any]]:
        now_utc = datetime.now(timezone.utc)

        # 1. Probe current group ID
        try:
            data = await self._fetch_decrypted(client, f"{self.BASE_URL}/groups/{self.group_id}")
            if self._is_group_active(data, now_utc):
                return self.group_id, data
        except Exception:
            pass

        # 2. Forward scan if month rolled over
        for offset in range(1, 25):
            candidate_gid = self.group_id + offset
            try:
                data = await self._fetch_decrypted(client, f"{self.BASE_URL}/groups/{candidate_gid}")
                name = str(data.get("name", "")).lower()
                if ("spin&gold" in name or "spin & gold" in name) and self._is_group_active(data, now_utc):
                    self.group_id = candidate_gid
                    return candidate_gid, data
            except Exception:
                continue

        # 3. Fallback: return data for default group if fetch succeeds
        data = await self._fetch_decrypted(client, f"{self.BASE_URL}/groups/{self.group_id}")
        return self.group_id, data

    async def get_active_promotions(self, force: bool = False) -> Tuple[int, str, Dict[str, Any]]:
        now = time.time()
        cached_ts, cached_gid, cached_name, cached_promos = self._promo_cache
        if not force and cached_promos and (now - cached_ts < self.group_ttl):
            return cached_gid, cached_name, cached_promos

        async with self._group_lock:
            now = time.time()
            cached_ts, cached_gid, cached_name, cached_promos = self._promo_cache
            if not force and cached_promos and (now - cached_ts < self.group_ttl):
                return cached_gid, cached_name, cached_promos

            try:
                async with httpx.AsyncClient(headers=self.DEFAULT_HEADERS) as client:
                    gid, group_data = await self._find_active_group(client)

                group_name = group_data.get("name", "Daily $50,000 Leaderboard (Spin&Gold)")
                now_utc = datetime.now(timezone.utc)
                promo_map: Dict[str, Any] = {}

                for p_item in group_data.get("promotions", []):
                    promo = p_item.get("promotion", {})
                    name = promo.get("name", "")
                    pid = p_item.get("promotionId")
                    s_str = promo.get("startedAt")
                    f_str = promo.get("finishedAt")
                    status = promo.get("status", "RUNNING")

                    is_active = False
                    if s_str and f_str:
                        try:
                            s_dt = datetime.fromisoformat(s_str)
                            f_dt = datetime.fromisoformat(f_str)
                            if s_dt <= now_utc <= f_dt:
                                is_active = True
                        except Exception:
                            pass
                    if not is_active and status == "RUNNING":
                        is_active = True

                    if is_active:
                        stake = self._extract_stake(name)
                        if stake:
                            total_prz = float(promo.get("totalPrizeValue") or 0.0)
                            promo_map[stake] = {
                                "stake": stake,
                                "promotion_id": pid,
                                "name": name,
                                "group_id": gid,
                                "total_prize": total_prz,
                                "prize_pool": f"${total_prz:,.0f}" if total_prz.is_integer() else f"${total_prz:,.2f}",
                                "status": status,
                                "started_at": s_str,
                                "finished_at": f_str
                            }

                self._promo_cache = (now, gid, group_name, promo_map)
                return gid, group_name, promo_map

            except Exception as e:
                # If cached promotions exist, return stale cache during network degradation
                if cached_promos:
                    return cached_gid, cached_name, cached_promos
                raise RuntimeError(f"Unable to discover active promotions from GGPoker: {e}") from e

    async def get_active_stakes(self, force: bool = False) -> StakesResponse:
        gid, gname, promos = await self.get_active_promotions(force=force)
        cutoff_dt, _, _ = compute_cutoff()

        items: List[StakeItem] = []
        for stake in SUPPORTED_STAKES:
            if stake in promos:
                p = promos[stake]
                items.append(StakeItem(
                    stake=p["stake"],
                    promotion_id=p["promotion_id"],
                    name=p["name"],
                    group_id=p["group_id"],
                    prize_pool=p["prize_pool"],
                    total_prize=p["total_prize"],
                    status=p["status"],
                    started_at=p["started_at"],
                    finished_at=p["finished_at"]
                ))
            else:
                # Include entry even if not found in promo map with fallback placeholder
                items.append(StakeItem(
                    stake=stake,
                    promotion_id=0,
                    name=f"Spin & Gold {stake}",
                    group_id=gid,
                    prize_pool="$0",
                    total_prize=0.0,
                    status="OFFLINE"
                ))

        cached_flag = (time.time() - self._promo_cache[0]) > 1.0

        return StakesResponse(
            group_id=gid,
            group_name=gname,
            cutoff_utc=cutoff_dt.isoformat(),
            cached=cached_flag,
            stakes=items
        )

    async def get_leaderboard(
        self,
        stake: str,
        hero_query: Optional[str] = None,
        limit: int = 50,
        force: bool = False
    ) -> LeaderboardResponse:
        stake_norm = normalize_stake_str(stake)
        now = time.time()

        cached_entry = self._rank_cache.get(stake_norm)
        if not force and cached_entry and (now - cached_entry["timestamp"] < self.rank_ttl):
            return self._build_leaderboard_response(
                stake=stake_norm,
                cached_entry=cached_entry,
                hero_query=hero_query,
                cached_flag=True
            )

        lock = self._get_stake_lock(stake_norm)
        async with lock:
            now = time.time()
            cached_entry = self._rank_cache.get(stake_norm)
            if not force and cached_entry and (now - cached_entry["timestamp"] < self.rank_ttl):
                return self._build_leaderboard_response(
                    stake=stake_norm,
                    cached_entry=cached_entry,
                    hero_query=hero_query,
                    cached_flag=True
                )

            # Get promotion for this stake
            _, _, promos = await self.get_active_promotions()
            promo_info = promos.get(stake_norm)

            if not promo_info:
                # Force refresh promos once in case of rollover
                _, _, promos = await self.get_active_promotions(force=True)
                promo_info = promos.get(stake_norm)

            if not promo_info:
                raise ValueError(f"Stake '{stake_norm}' is not available in active promotions.")

            pid = promo_info["promotion_id"]
            finished_at = promo_info.get("finished_at")
            url = f"{self.BASE_URL}/{pid}/?limit={limit}&hasSummary=true"

            try:
                async with httpx.AsyncClient(headers=self.DEFAULT_HEADERS) as client:
                    raw_players = await self._fetch_decrypted(client, url)

                if not isinstance(raw_players, list):
                    raise ValueError(f"Expected list of players, got {type(raw_players)}")

                cached_entry = {
                    "timestamp": time.time(),
                    "promotion_id": pid,
                    "finished_at": finished_at,
                    "raw_players": raw_players
                }
                self._rank_cache[stake_norm] = cached_entry

                return self._build_leaderboard_response(
                    stake=stake_norm,
                    cached_entry=cached_entry,
                    hero_query=hero_query,
                    cached_flag=False
                )

            except Exception as e:
                # Fallback to stale cache if available
                if cached_entry:
                    return self._build_leaderboard_response(
                        stake=stake_norm,
                        cached_entry=cached_entry,
                        hero_query=hero_query,
                        cached_flag=True
                    )
                raise RuntimeError(f"Failed to fetch leaderboard for stake '{stake_norm}': {e}") from e

    def _build_leaderboard_response(
        self,
        stake: str,
        cached_entry: Dict[str, Any],
        hero_query: Optional[str],
        cached_flag: bool
    ) -> LeaderboardResponse:
        now_ts = time.time()
        entry_ts = cached_entry.get("timestamp", now_ts)
        cache_age = max(0.0, round(now_ts - entry_ts, 2))
        pid = cached_entry.get("promotion_id")
        fin_at = cached_entry.get("finished_at")
        raw_players = cached_entry.get("raw_players", [])

        cutoff_dt, seconds_remaining, _ = compute_cutoff(finished_at=fin_at)

        player_entries, hero_idx = build_player_entries(raw_players, hero_query=hero_query)
        hero_telemetry = calculate_hero_telemetry(player_entries, hero_idx, hero_query=hero_query)

        updated_at = datetime.fromtimestamp(entry_ts, tz=timezone.utc).isoformat()

        return LeaderboardResponse(
            stake=stake,
            promotion_id=pid,
            updated_at=updated_at,
            cutoff_utc=cutoff_dt.isoformat(),
            cutoff_seconds=seconds_remaining,
            cutoff_seconds_remaining=seconds_remaining,
            cached=cached_flag,
            cache_age_sec=cache_age,
            total_players=len(player_entries),
            hero=hero_telemetry,
            players=player_entries,
            leaderboard=player_entries
        )

# Global client singleton
_gg_client: Optional[GGClient] = None

def get_gg_client() -> GGClient:
    global _gg_client
    if _gg_client is None:
        _gg_client = GGClient()
    return _gg_client
