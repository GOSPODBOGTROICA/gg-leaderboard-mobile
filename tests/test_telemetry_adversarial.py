import math
import pytest
from datetime import datetime, timezone, timedelta
from app.telemetry import (
    compute_cutoff,
    parse_prize,
    build_player_entries,
    calculate_hero_telemetry,
)
from app.models import HeroTelemetry, PlayerEntry, PrizeInfo

# ==============================================================================
# 1. HERO AT RANK #1 STRESS TESTS
# ==============================================================================

def test_hero_rank_1_with_comfortable_lead():
    raw_players = [
        {"rank": 1, "nickname": "Hero_1", "point": "2500.0", "prize": {"value": 100}},
        {"rank": 2, "nickname": "Player_2", "point": "2400.0", "prize": {"value": 60}},
        {"rank": 3, "nickname": "Player_3", "point": "2300.0", "prize": {"value": 40}},
    ]
    entries, hero_idx = build_player_entries(raw_players, "Hero_1")
    telemetry = calculate_hero_telemetry(entries, hero_idx, "Hero_1")

    assert telemetry is not None
    assert telemetry.found is True
    assert telemetry.rank == 1
    assert telemetry.pts_to_next == 0.0
    assert telemetry.target_rank is None
    assert telemetry.prize_diff_to_next == 0.0
    assert telemetry.estimated_wins_to_next == 0
    assert telemetry.lead_over_prev == 100.0  # 2500 - 2400
    assert telemetry.trailing_rank == 2
    assert telemetry.cushion_danger is False  # 100 >= 20.0
    assert "👑 Лидер гонки!" in telemetry.status_text
    assert "+100.0 pts" in telemetry.status_text

def test_hero_rank_1_with_fragile_lead_triggers_cushion_danger():
    # Lead is 12.5 pts (< 20 pts threshold)
    raw_players = [
        {"rank": 1, "nickname": "Hero_1", "point": "2500.0", "prize": {"value": 100}},
        {"rank": 2, "nickname": "Chaser", "point": "2487.5", "prize": {"value": 60}},
    ]
    entries, hero_idx = build_player_entries(raw_players, "Hero_1")
    telemetry = calculate_hero_telemetry(entries, hero_idx, "Hero_1")

    assert telemetry.found is True
    assert telemetry.rank == 1
    assert telemetry.pts_to_next == 0.0
    assert telemetry.lead_over_prev == 12.5
    assert telemetry.trailing_rank == 2
    assert telemetry.cushion_danger is True  # 12.5 < 20.0

# ==============================================================================
# 2. HERO ACROSS ALL RANKS #2..49 FULL SWEEP
# ==============================================================================

def test_hero_all_intermediate_ranks_2_to_49_sweep():
    """
    Stress-tests the full progression across all 48 intermediate positions (2..49)
    in a realistic 50-player leaderboard.
    """
    # Create 50 players with descending points and prizes
    # Points decrease by varying gaps from 5000.0 down to ~500.0
    raw_players = []
    base_points = 5000.0
    for r in range(1, 51):
        # variable gaps: alternate between 15.0 and 35.0
        gap = 15.0 if r % 2 == 0 else 35.0
        base_points -= gap
        raw_players.append({
            "rank": r,
            "nickname": f"Player_{r}",
            "point": f"{base_points:.2f}",
            "prize": {"value": max(5, 200 - r * 3)}
        })

    # Test every single rank from 2 to 49
    for target_r in range(2, 50):
        hero_nick = f"Player_{target_r}"
        entries, hero_idx = build_player_entries(raw_players, hero_nick)
        telemetry = calculate_hero_telemetry(entries, hero_idx, hero_nick)

        assert telemetry is not None, f"Telemetry None for rank {target_r}"
        assert telemetry.found is True
        assert telemetry.rank == target_r
        assert telemetry.target_rank == target_r - 1, f"Expected target_rank {target_r-1}, got {telemetry.target_rank}"
        assert telemetry.trailing_rank == target_r + 1, f"Expected trailing_rank {target_r+1}, got {telemetry.trailing_rank}"

        expected_pts_to_next = round(float(raw_players[target_r - 2]["point"]) - float(raw_players[target_r - 1]["point"]), 2)
        expected_lead = round(float(raw_players[target_r - 1]["point"]) - float(raw_players[target_r]["point"]), 2)

        assert telemetry.pts_to_next == expected_pts_to_next
        assert telemetry.lead_over_prev == expected_lead
        assert telemetry.cushion_danger == (expected_lead < 20.0)
        assert telemetry.estimated_wins_to_next == max(1, math.ceil(expected_pts_to_next / 2.5))

# ==============================================================================
# 3. HERO AT RANK #50 (BOUNDARY & BUBBLE DANGER)
# ==============================================================================

def test_hero_at_rank_50_boundary():
    raw_players = [
        {"rank": i, "nickname": f"P_{i}", "point": f"{2000 - i * 20}.0", "prize": {"value": 10}}
        for i in range(1, 51)
    ]
    raw_players[49]["nickname"] = "Hero_50"

    entries, hero_idx = build_player_entries(raw_players, "Hero_50")
    telemetry = calculate_hero_telemetry(entries, hero_idx, "Hero_50")

    assert telemetry.found is True
    assert telemetry.rank == 50
    assert telemetry.target_rank == 49
    assert telemetry.pts_to_next == 20.0  # (2000 - 49*20) - (2000 - 50*20) = 20.0
    assert telemetry.lead_over_prev is None  # Nobody behind in Top-50
    assert telemetry.trailing_rank == 51
    assert telemetry.cushion_danger is True  # Bubble danger ALWAYS active
    assert "⚠️ На краю Топ-50!" in telemetry.status_text
    assert "Опасность вылета из призов!" in telemetry.status_text

# ==============================================================================
# 4. HERO UNRANKED / NOT IN TOP-50
# ==============================================================================

def test_hero_unranked_standard_top_50():
    raw_players = [
        {"rank": i, "nickname": f"P_{i}", "point": f"{3000 - i * 15}.0", "prize": {"value": 10}}
        for i in range(1, 51)
    ]
    rank_50_pts = float(raw_players[49]["point"])  # 3000 - 750 = 2250.0

    entries, hero_idx = build_player_entries(raw_players, "StrangerNick")
    telemetry = calculate_hero_telemetry(entries, hero_idx, "StrangerNick")

    assert telemetry.found is False
    assert telemetry.rank is None
    assert telemetry.points is None
    assert telemetry.target_rank == 50
    assert telemetry.pts_to_next == rank_50_pts
    assert telemetry.lead_over_prev is None
    assert telemetry.trailing_rank is None
    assert telemetry.cushion_danger is False
    assert telemetry.estimated_wins_to_next == math.ceil(rank_50_pts / 2.5)
    assert f"Порог входа (#50): {rank_50_pts:.1f} pts" in telemetry.status_text

def test_hero_unranked_on_partial_leaderboard():
    # High stakes ($100 / $200) sometimes have only 7 active players
    raw_players = [
        {"rank": i, "nickname": f"Whale_{i}", "point": f"{1000 - i * 50}.0", "prize": {"value": 500}}
        for i in range(1, 8)
    ]
    rank_7_pts = float(raw_players[6]["point"])  # 650.0

    entries, hero_idx = build_player_entries(raw_players, "SmallFish")
    telemetry = calculate_hero_telemetry(entries, hero_idx, "SmallFish")

    assert telemetry.found is False
    assert telemetry.target_rank == 7
    assert telemetry.pts_to_next == rank_7_pts
    assert f"Порог входа (#7): {rank_7_pts:.1f} pts" in telemetry.status_text

# ==============================================================================
# 5. EDGE CASES: TIED POINTS, FRACTIONAL POINTS, EMPTY & SINGLE-PLAYER BOARDS
# ==============================================================================

def test_edge_case_tied_points_at_rank_1():
    raw_players = [
        {"rank": 1, "nickname": "Hero_Tied1", "point": "1500.0", "prize": {"value": 50}},
        {"rank": 2, "nickname": "Rival_Tied1", "point": "1500.0", "prize": {"value": 30}},
        {"rank": 3, "nickname": "Player_3", "point": "1200.0", "prize": {"value": 20}},
    ]
    entries, hero_idx = build_player_entries(raw_players, "Hero_Tied1")
    telemetry = calculate_hero_telemetry(entries, hero_idx, "Hero_Tied1")

    assert telemetry.rank == 1
    assert telemetry.pts_to_next == 0.0
    assert telemetry.lead_over_prev == 0.0  # 1500 - 1500
    assert telemetry.cushion_danger is True  # 0.0 < 20.0 triggers cushion alert!

def test_edge_case_tied_points_intermediate():
    raw_players = [
        {"rank": 1, "nickname": "Leader", "point": "1800.0", "prize": {"value": 50}},
        {"rank": 2, "nickname": "P2", "point": "1400.0", "prize": {"value": 30}},
        {"rank": 3, "nickname": "Hero_Tied", "point": "1400.0", "prize": {"value": 20}},
        {"rank": 4, "nickname": "P4", "point": "1400.0", "prize": {"value": 15}},
        {"rank": 5, "nickname": "P5", "point": "1000.0", "prize": {"value": 10}},
    ]
    entries, hero_idx = build_player_entries(raw_players, "Hero_Tied")
    telemetry = calculate_hero_telemetry(entries, hero_idx, "Hero_Tied")

    assert telemetry.rank == 3
    assert telemetry.pts_to_next == 0.0  # Tied with rank 2
    assert telemetry.estimated_wins_to_next == 0
    assert telemetry.lead_over_prev == 0.0  # Tied with rank 4
    assert telemetry.cushion_danger is True  # 0.0 < 20.0

def test_edge_case_entire_field_tied():
    raw_players = [
        {"rank": i, "nickname": f"Bot_{i}", "point": "100.0", "prize": {"value": 5}}
        for i in range(1, 51)
    ]
    # Check Rank 1
    e1, idx1 = build_player_entries(raw_players, "Bot_1")
    t1 = calculate_hero_telemetry(e1, idx1, "Bot_1")
    assert t1.pts_to_next == 0.0
    assert t1.lead_over_prev == 0.0

    # Check Rank 25
    e25, idx25 = build_player_entries(raw_players, "Bot_25")
    t25 = calculate_hero_telemetry(e25, idx25, "Bot_25")
    assert t25.pts_to_next == 0.0
    assert t25.lead_over_prev == 0.0
    assert t25.estimated_wins_to_next == 0

    # Check Rank 50
    e50, idx50 = build_player_entries(raw_players, "Bot_50")
    t50 = calculate_hero_telemetry(e50, idx50, "Bot_50")
    assert t50.pts_to_next == 0.0
    assert t50.lead_over_prev is None
    assert t50.cushion_danger is True

def test_edge_case_floating_point_precision_rounding():
    # In IEEE-754, 1000.07 - 1000.03 = 0.040000000000077307
    raw_players = [
        {"rank": 1, "nickname": "P1", "point": "1000.07", "prize": {"value": 50}},
        {"rank": 2, "nickname": "Hero_Float", "point": "1000.03", "prize": {"value": 30}},
        {"rank": 3, "nickname": "P3", "point": "999.89", "prize": {"value": 20}},
    ]
    entries, hero_idx = build_player_entries(raw_players, "Hero_Float")
    telemetry = calculate_hero_telemetry(entries, hero_idx, "Hero_Float")

    assert telemetry.pts_to_next == 0.04
    assert telemetry.lead_over_prev == 0.14  # 1000.03 - 999.89 = 0.14
    # Ensure exact float equality to 2 decimals, not nasty IEEE artifact
    assert str(telemetry.pts_to_next) == "0.04"
    assert str(telemetry.lead_over_prev) == "0.14"

def test_edge_case_empty_leaderboard():
    raw_players = []
    entries, hero_idx = build_player_entries(raw_players, "GhostPlayer")
    assert entries == []
    assert hero_idx is None

    telemetry = calculate_hero_telemetry(entries, hero_idx, "GhostPlayer")
    assert telemetry.found is False
    assert telemetry.target_rank == 50
    assert telemetry.pts_to_next == 0.0
    assert telemetry.lead_over_prev is None
    assert telemetry.estimated_wins_to_next == 0
    assert "Топ-0" in telemetry.status_text

def test_edge_case_single_player_leaderboard():
    # Only 1 player in the entire stake (e.g. at 08:00:01 right after daily reset)
    raw_players = [{"rank": 1, "nickname": "SoloHero", "point": "50.0", "prize": {"value": 10}}]

    # Subcase A: Hero is that single player
    entries, hero_idx = build_player_entries(raw_players, "SoloHero")
    telemetry = calculate_hero_telemetry(entries, hero_idx, "SoloHero")
    assert telemetry.found is True
    assert telemetry.rank == 1
    assert telemetry.pts_to_next == 0.0
    assert telemetry.target_rank is None
    assert telemetry.lead_over_prev is None
    assert telemetry.trailing_rank is None
    assert telemetry.cushion_danger is False
    assert telemetry.status_text == "👑 Лидер гонки!"

    # Subcase B: Hero is NOT that single player
    entries2, hero_idx2 = build_player_entries(raw_players, "UnrankedGuy")
    telemetry2 = calculate_hero_telemetry(entries2, hero_idx2, "UnrankedGuy")
    assert telemetry2.found is False
    assert telemetry2.target_rank == 1
    assert telemetry2.pts_to_next == 50.0
    assert telemetry2.estimated_wins_to_next == 20

def test_edge_case_two_player_leaderboard():
    raw_players = [
        {"rank": 1, "nickname": "P1", "point": "120.0", "prize": {"value": 20}},
        {"rank": 2, "nickname": "P2", "point": "80.0", "prize": {"value": 10}},
    ]
    # Hero is Rank 1
    e1, idx1 = build_player_entries(raw_players, "P1")
    t1 = calculate_hero_telemetry(e1, idx1, "P1")
    assert t1.rank == 1
    assert t1.pts_to_next == 0.0
    assert t1.lead_over_prev == 40.0
    assert t1.trailing_rank == 2

    # Hero is Rank 2 (simultaneously Rank 2 and bottom player)
    e2, idx2 = build_player_entries(raw_players, "P2")
    t2 = calculate_hero_telemetry(e2, idx2, "P2")
    assert t2.rank == 2
    assert t2.target_rank == 1
    assert t2.pts_to_next == 40.0
    assert t2.lead_over_prev is None
    assert t2.trailing_rank == 3
    assert t2.cushion_danger is True

def test_edge_case_whitespace_and_exact_match_priority():
    raw_players = [
        {"rank": 1, "nickname": "Shark_PRO", "point": "500.0"},
        {"rank": 2, "nickname": "Shark", "point": "400.0"},
    ]
    # Exact match for "Shark" should choose rank 2 even though "Shark_PRO" contains "Shark"
    entries, hero_idx = build_player_entries(raw_players, "   sHarK   ")
    assert hero_idx == 1
    telemetry = calculate_hero_telemetry(entries, hero_idx, "   sHarK   ")
    assert telemetry.rank == 2
    assert telemetry.pts_to_next == 100.0

def test_edge_case_blank_or_whitespace_only_nickname():
    raw_players = [{"rank": 1, "nickname": "P1", "point": "100.0"}]
    entries, hero_idx = build_player_entries(raw_players, "   ")
    assert hero_idx is None
    telemetry = calculate_hero_telemetry(entries, hero_idx, "   ")
    assert telemetry is None

# ==============================================================================
# 6. CUTOFF COUNTDOWN CALCULATION STRESS TESTS (UTC BOUNDARIES)
# ==============================================================================

def test_cutoff_midnight_utc_transition():
    """
    Tests continuity across 23:59:58 -> 23:59:59 -> 00:00:00 -> 00:00:01 UTC.
    The remaining countdown must decrease strictly monotonically by exactly 1s.
    """
    t_235958 = datetime(2026, 10, 13, 23, 59, 58, tzinfo=timezone.utc)
    t_235959 = datetime(2026, 10, 13, 23, 59, 59, tzinfo=timezone.utc)
    t_000000 = datetime(2026, 10, 14, 0, 0, 0, tzinfo=timezone.utc)
    t_000001 = datetime(2026, 10, 14, 0, 0, 1, tzinfo=timezone.utc)

    c1, s1, f1 = compute_cutoff(now=t_235958)
    c2, s2, f2 = compute_cutoff(now=t_235959)
    c3, s3, f3 = compute_cutoff(now=t_000000)
    c4, s4, f4 = compute_cutoff(now=t_000001)

    # All target cutoffs must point to 2026-10-14 08:00:00 UTC
    expected_cutoff = datetime(2026, 10, 14, 8, 0, 0, tzinfo=timezone.utc)
    assert c1 == expected_cutoff
    assert c2 == expected_cutoff
    assert c3 == expected_cutoff
    assert c4 == expected_cutoff

    # Decreasing by exactly 1 second
    assert s1 == 28802
    assert s2 == 28801
    assert s3 == 28800
    assert s4 == 28799

    assert s1 - s2 == 1
    assert s2 - s3 == 1
    assert s3 - s4 == 1

    assert f3 == "08ч 00м 00с"
    assert f4 == "07ч 59м 59с"

def test_cutoff_reset_boundary_transitions():
    """
    Tests step transition across the daily reset point:
    07:59:58 -> 07:59:59 -> 08:00:00 -> 08:00:01 UTC.
    """
    t_075958 = datetime(2026, 10, 13, 7, 59, 58, tzinfo=timezone.utc)
    t_075959 = datetime(2026, 10, 13, 7, 59, 59, tzinfo=timezone.utc)
    t_080000 = datetime(2026, 10, 13, 8, 0, 0, tzinfo=timezone.utc)
    t_080001 = datetime(2026, 10, 13, 8, 0, 1, tzinfo=timezone.utc)

    # 1. At 07:59:58: 2 seconds left in current day
    c1, s1, f1 = compute_cutoff(now=t_075958)
    assert c1 == datetime(2026, 10, 13, 8, 0, 0, tzinfo=timezone.utc)
    assert s1 == 2
    assert f1 == "00ч 00м 02с"

    # 2. At 07:59:59: 1 second left in current day
    c2, s2, f2 = compute_cutoff(now=t_075959)
    assert c2 == datetime(2026, 10, 13, 8, 0, 0, tzinfo=timezone.utc)
    assert s2 == 1
    assert f2 == "00ч 00м 01с"

    # 3. At 08:00:00: Exactly at reset instant, flips to NEXT day 08:00:00 UTC (86400s)
    c3, s3, f3 = compute_cutoff(now=t_080000)
    assert c3 == datetime(2026, 10, 14, 8, 0, 0, tzinfo=timezone.utc)
    assert s3 == 86400
    assert f3 == "24ч 00м 00с"

    # 4. At 08:00:01: 86399 seconds left in next day
    c4, s4, f4 = compute_cutoff(now=t_080001)
    assert c4 == datetime(2026, 10, 14, 8, 0, 0, tzinfo=timezone.utc)
    assert s4 == 86399
    assert f4 == "23ч 59м 59с"

def test_cutoff_subsecond_microsecond_precision():
    # 07:59:59.999999 -> 0 seconds left
    t_sub = datetime(2026, 10, 13, 7, 59, 59, 999999, tzinfo=timezone.utc)
    _, s_sub, f_sub = compute_cutoff(now=t_sub)
    assert s_sub == 0
    assert f_sub == "00ч 00м 00с"

def test_cutoff_tz_naive_datetime_handling():
    # Naive datetime should be treated as UTC without exception
    t_naive = datetime(2026, 10, 13, 7, 30, 0)
    cutoff_dt, secs, formatted = compute_cutoff(now=t_naive)
    assert secs == 1800
    assert formatted == "00ч 30м 00с"
    assert cutoff_dt.tzinfo == timezone.utc

def test_cutoff_non_utc_timezone_awareness():
    # UTC+3 MSK time: 10:30:00 MSK == 07:30:00 UTC -> 30 mins (1800s) to 08:00 UTC
    tz_msk = timezone(timedelta(hours=3))
    t_msk = datetime(2026, 10, 13, 10, 30, 0, tzinfo=tz_msk)
    cutoff_dt, secs, formatted = compute_cutoff(now=t_msk)
    assert secs == 1800
    assert formatted == "00ч 30м 00с"

def test_edge_case_tied_at_bubble_rank_50():
    raw_players = [
        {"rank": i, "nickname": f"P_{i}", "point": f"{1000 - i * 10}.0", "prize": {"value": 10}}
        for i in range(1, 51)
    ]
    # Tie rank 49 and rank 50 with exact same points
    raw_players[48]["point"] = "510.0"
    raw_players[49]["point"] = "510.0"
    raw_players[49]["nickname"] = "Hero_Bubble_Tied"

    entries, hero_idx = build_player_entries(raw_players, "Hero_Bubble_Tied")
    telemetry = calculate_hero_telemetry(entries, hero_idx, "Hero_Bubble_Tied")

    assert telemetry.rank == 50
    assert telemetry.pts_to_next == 0.0  # Tied with rank 49
    assert telemetry.estimated_wins_to_next == 0
    assert telemetry.lead_over_prev is None
    assert telemetry.trailing_rank == 51
    assert telemetry.cushion_danger is True

def test_edge_case_zero_and_very_large_points():
    raw_players = [
        {"rank": 1, "nickname": "WhaleLeader", "point": "15000000.55", "prize": {"value": 500}},
        {"rank": 2, "nickname": "GrinderMid", "point": "5000000.25", "prize": {"value": 250}},
        {"rank": 3, "nickname": "BrokeGuy", "point": "0.0", "prize": None},
    ]
    # Test Whale
    e1, idx1 = build_player_entries(raw_players, "WhaleLeader")
    t1 = calculate_hero_telemetry(e1, idx1, "WhaleLeader")
    assert t1.lead_over_prev == 10000000.30

    # Test BrokeGuy at Rank 3
    e3, idx3 = build_player_entries(raw_players, "BrokeGuy")
    t3 = calculate_hero_telemetry(e3, idx3, "BrokeGuy")
    assert t3.rank == 3
    assert t3.pts_to_next == 5000000.25
    assert t3.points == 0.0

def test_cutoff_year_boundary_transition():
    # 2026-12-31 23:59:59 UTC -> Cutoff should be 2027-01-01 08:00:00 UTC (8h 1s = 28801s)
    t_nye = datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    cutoff_dt, secs, formatted = compute_cutoff(now=t_nye)
    assert cutoff_dt == datetime(2027, 1, 1, 8, 0, 0, tzinfo=timezone.utc)
    assert secs == 28801
    assert formatted == "08ч 00м 01с"

def test_prize_parsing_defensive_edge_cases():
    assert parse_prize(None) is None
    assert parse_prize({}) is None
    assert parse_prize({"value": 0}) is None
    assert parse_prize({"value": -100}) is None

    p_cash = parse_prize({"value": 150.0})
    assert p_cash.type == "CASH"
    assert p_cash.text == "$150"
    assert p_cash.value == 150.0

    p_cash_dec = parse_prize({"value": 12.5})
    assert p_cash_dec.text == "$12.50"

    p_tkt_single = parse_prize({"value": 10, "prizeItem": [{"type": "TICKET", "quantity": 1, "value": 10}]})
    assert p_tkt_single.text == "$10 Ticket"

    p_tkt_multi = parse_prize({"value": 50, "prizeItem": [{"type": "TICKET", "quantity": 5, "value": 10}]})
    assert p_tkt_multi.text == "$50 (5×$10 Tickets)"

