import math
from datetime import datetime, timezone, time, timedelta
from typing import List, Optional, Tuple, Dict, Any
from app.models import HeroTelemetry, PlayerEntry, PrizeInfo

def compute_cutoff(finished_at: Optional[str] = None, now: Optional[datetime] = None) -> Tuple[datetime, int, str]:
    """
    Calculates target cutoff datetime (08:00:00 UTC daily reset),
    exact seconds remaining, and formatted countdown string.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    cutoff_dt: Optional[datetime] = None

    # 1. If finished_at is provided, try parsing it
    if finished_at:
        try:
            fin = datetime.fromisoformat(finished_at)
            if fin.tzinfo is None:
                fin = fin.replace(tzinfo=timezone.utc)
            else:
                fin = fin.astimezone(timezone.utc)
            if fin > now:
                cutoff_dt = fin
        except Exception:
            pass

    # 2. If finished_at is not applicable or in the past, calculate next 08:00:00 UTC
    if cutoff_dt is None:
        target_today = now.replace(hour=8, minute=0, second=0, microsecond=0)
        if now < target_today:
            cutoff_dt = target_today
        else:
            cutoff_dt = target_today + timedelta(days=1)

    seconds_remaining = max(0, int((cutoff_dt - now).total_seconds()))

    hours = seconds_remaining // 3600
    minutes = (seconds_remaining % 3600) // 60
    secs = seconds_remaining % 60
    formatted_str = f"{hours:02d}ч {minutes:02d}м {secs:02d}с"

    return cutoff_dt, seconds_remaining, formatted_str

def parse_prize(p_raw: Optional[Dict[str, Any]]) -> Optional[PrizeInfo]:
    """
    Defensively parses raw GG prize dictionary or None.
    Handles 'type': 'TICKET' or cash, quantities, and nulls.
    """
    if not p_raw or not isinstance(p_raw, dict):
        return None

    val = float(p_raw.get("value") or 0.0)
    if val <= 0:
        return None

    currency = p_raw.get("currencyId", "USD")
    items = p_raw.get("prizeItem", [])
    p_type = "CASH"
    p_qty = None
    p_text = f"${val:,.0f}" if val.is_integer() else f"${val:,.2f}"

    if items and isinstance(items, list) and len(items) > 0:
        first_item = items[0]
        p_type = first_item.get("type", "TICKET")
        p_qty = first_item.get("quantity")
        unit_val = first_item.get("value", 1)
        if p_type == "TICKET":
            if p_qty and p_qty > 1:
                p_text = f"${val:,.0f} ({p_qty}×${unit_val} Tickets)"
            else:
                p_text = f"${val:,.0f} Ticket"

    return PrizeInfo(
        type=p_type,
        text=p_text,
        value=val,
        currency=currency,
        quantity=p_qty
    )

def build_player_entries(raw_players: List[Dict[str, Any]], hero_query: Optional[str] = None) -> Tuple[List[PlayerEntry], Optional[int]]:
    """
    Converts raw player rankings into standardized PlayerEntry models.
    Calculates gaps between players, parses prizes, and identifies hero index.
    """
    entries: List[PlayerEntry] = []
    hero_clean = hero_query.strip().lower() if hero_query else None
    matched_hero_idx: Optional[int] = None

    # First pass: identify exact or substring match index
    if hero_clean:
        # Exact match
        for idx, p in enumerate(raw_players):
            nick = str(p.get("nickname") or "").strip().lower()
            if nick == hero_clean:
                matched_hero_idx = idx
                break
        # Substring fallback
        if matched_hero_idx is None:
            for idx, p in enumerate(raw_players):
                nick = str(p.get("nickname") or "").strip().lower()
                if hero_clean in nick:
                    matched_hero_idx = idx
                    break

    # Build entries
    for idx, p in enumerate(raw_players):
        rank = p.get("rank", idx + 1)
        nick = str(p.get("nickname") or "").strip()
        pts = float(p.get("point") or 0.0)
        country = p.get("countryId") or p.get("country")
        prize = parse_prize(p.get("prize"))
        prize_str = prize.text if prize else "-"

        gap_to_prev = 0.0
        if idx > 0:
            prev_pts = float(raw_players[idx - 1].get("point") or 0.0)
            gap_to_prev = round(max(0.0, prev_pts - pts), 2)

        is_hero = (idx == matched_hero_idx)

        entries.append(PlayerEntry(
            rank=rank,
            nickname=nick,
            points=pts,
            country=country,
            prize=prize,
            prize_str=prize_str,
            gain_delta=None,
            gap_to_prev=gap_to_prev,
            is_hero=is_hero
        ))

    return entries, matched_hero_idx

def calculate_hero_telemetry(
    entries: List[PlayerEntry],
    matched_idx: Optional[int],
    hero_query: Optional[str]
) -> Optional[HeroTelemetry]:
    """
    Calculates detailed Hero telemetry math including:
    - pts_to_next
    - lead_over_prev
    - boundary Rank #1 (pts_to_next = 0, lead over #2)
    - boundary Rank #50 (bubble danger, lead_over_prev = None)
    - unranked player (target rank 50 gate)
    - tied points handling
    """
    if not hero_query or not hero_query.strip():
        return None

    clean_query = hero_query.strip()
    total_players = len(entries)

    # --- Scenario 1: Hero NOT found in rankings ---
    if matched_idx is None or matched_idx < 0 or matched_idx >= total_players:
        target_rank = 50
        pts_to_next = 0.0
        target_prize = None

        if total_players > 0:
            target_entry = entries[-1]
            target_rank = target_entry.rank
            pts_to_next = target_entry.points
            target_prize = target_entry.prize

        status_text = (
            f"🔍 Ник '{clean_query}' не найден в Топ-{total_players}. "
            f"Порог входа (#{target_rank}): {pts_to_next:.1f} pts"
        )

        return HeroTelemetry(
            nickname=clean_query,
            found=False,
            rank=None,
            points=None,
            prize=None,
            prize_value=None,
            prize_type=None,
            target_rank=target_rank,
            pts_to_next=pts_to_next,
            prize_diff_to_next=target_prize.value if target_prize else 0.0,
            estimated_wins_to_next=max(1, math.ceil(pts_to_next / 2.5)) if pts_to_next > 0 else 0,
            trailing_rank=None,
            lead_over_prev=None,
            cushion_danger=False,
            status_text=status_text,
            target_prize=target_prize
        )

    # --- Scenario 2: Hero Found in rankings ---
    hero_entry = entries[matched_idx]
    hero_rank = hero_entry.rank
    hero_pts = hero_entry.points
    hero_prize = hero_entry.prize
    hero_prz_val = hero_prize.value if hero_prize else 0.0
    hero_prz_type = hero_prize.type if hero_prize else None

    target_rank: Optional[int] = None
    pts_to_next: Optional[float] = None
    prize_diff_to_next: Optional[float] = None
    estimated_wins_to_next: Optional[int] = None
    target_prize: Optional[PrizeInfo] = None

    trailing_rank: Optional[int] = None
    lead_over_prev: Optional[float] = None
    cushion_danger: bool = False
    status_text: str = ""

    # Case A: Rank #1
    if matched_idx == 0:
        pts_to_next = 0.0
        target_rank = None
        prize_diff_to_next = 0.0
        estimated_wins_to_next = 0

        if total_players > 1:
            next_entry = entries[1]
            trailing_rank = next_entry.rank
            lead_over_prev = round(max(0.0, hero_pts - next_entry.points), 2)
            cushion_danger = (lead_over_prev < 20.0)
            status_text = f"👑 Лидер гонки! Отрыв от #{trailing_rank}: +{lead_over_prev:.1f} pts"
        else:
            status_text = "👑 Лидер гонки!"

    # Case B: Rank 2 to 49
    elif 0 < matched_idx < (total_players - 1):
        prev_entry = entries[matched_idx - 1]
        target_rank = prev_entry.rank
        pts_to_next = round(max(0.0, prev_entry.points - hero_pts), 2)
        target_prize = prev_entry.prize
        prev_prz_val = target_prize.value if target_prize else 0.0
        prize_diff_to_next = max(0.0, prev_prz_val - hero_prz_val)
        estimated_wins_to_next = max(1, math.ceil(pts_to_next / 2.5)) if pts_to_next > 0 else 0

        next_entry = entries[matched_idx + 1]
        trailing_rank = next_entry.rank
        lead_over_prev = round(max(0.0, hero_pts - next_entry.points), 2)
        cushion_danger = (lead_over_prev < 20.0)

        gain_text = f" (+${prize_diff_to_next:.0f})" if prize_diff_to_next > 0 else ""
        status_text = (
            f"🎯 До #{target_rank}: +{pts_to_next:.1f} pts (~{estimated_wins_to_next} побед){gain_text} "
            f"| 🛡️ Отрыв от #{trailing_rank}: +{lead_over_prev:.1f} pts"
        )

    # Case C: Last Player (e.g. Rank 50 or bottom of list)
    else:
        prev_entry = entries[matched_idx - 1]
        target_rank = prev_entry.rank
        pts_to_next = round(max(0.0, prev_entry.points - hero_pts), 2)
        target_prize = prev_entry.prize
        prev_prz_val = target_prize.value if target_prize else 0.0
        prize_diff_to_next = max(0.0, prev_prz_val - hero_prz_val)
        estimated_wins_to_next = max(1, math.ceil(pts_to_next / 2.5)) if pts_to_next > 0 else 0

        trailing_rank = hero_rank + 1
        lead_over_prev = None
        cushion_danger = True

        status_text = (
            f"⚠️ На краю Топ-{total_players}! "
            f"До #{target_rank}: +{pts_to_next:.1f} pts | Опасность вылета из призов!"
        )

    return HeroTelemetry(
        nickname=hero_entry.nickname,
        found=True,
        rank=hero_rank,
        points=hero_pts,
        prize=hero_prize,
        prize_value=hero_prz_val,
        prize_type=hero_prz_type,
        target_rank=target_rank,
        pts_to_next=pts_to_next,
        prize_diff_to_next=prize_diff_to_next,
        estimated_wins_to_next=estimated_wins_to_next,
        trailing_rank=trailing_rank,
        lead_over_prev=lead_over_prev,
        cushion_danger=cushion_danger,
        status_text=status_text,
        target_prize=target_prize
    )
