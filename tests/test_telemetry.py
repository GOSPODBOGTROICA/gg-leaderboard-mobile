import pytest
from datetime import datetime, timezone
from app.telemetry import (
    compute_cutoff,
    build_player_entries,
    calculate_hero_telemetry,
)

def test_cutoff_countdown_math():
    # 07:59:59 UTC -> 1 second left
    t1 = datetime(2026, 10, 13, 7, 59, 59, tzinfo=timezone.utc)
    _, s1, f1 = compute_cutoff(now=t1)
    assert s1 == 1
    assert f1 == "00ч 00м 01с"

    # 08:00:00 UTC -> 86400 seconds left
    t2 = datetime(2026, 10, 13, 8, 0, 0, tzinfo=timezone.utc)
    _, s2, f2 = compute_cutoff(now=t2)
    assert s2 == 86400
    assert f2 == "24ч 00м 00с"

    # 08:00:01 UTC -> 86399 seconds left
    t3 = datetime(2026, 10, 13, 8, 0, 1, tzinfo=timezone.utc)
    _, s3, f3 = compute_cutoff(now=t3)
    assert s3 == 86399

def test_hero_rank_1_telemetry():
    raw_players = [
        {"rank": 1, "nickname": "Hero_1", "point": "1200.0", "prize": {"value": 50}},
        {"rank": 2, "nickname": "Player_2", "point": "1050.0", "prize": {"value": 30}},
        {"rank": 3, "nickname": "Player_3", "point": "900.0", "prize": {"value": 20}},
    ]
    entries, hero_idx = build_player_entries(raw_players, "Hero_1")
    telemetry = calculate_hero_telemetry(entries, hero_idx, "Hero_1")

    assert telemetry.found is True
    assert telemetry.rank == 1
    assert telemetry.pts_to_next == 0.0
    assert telemetry.target_rank is None
    assert telemetry.lead_over_prev == 150.0  # 1200 - 1050
    assert telemetry.trailing_rank == 2
    assert telemetry.cushion_danger is False

def test_hero_intermediate_rank_telemetry():
    raw_players = [
        {"rank": 1, "nickname": "Player_1", "point": "1500.0", "prize": {"value": 50}},
        {"rank": 2, "nickname": "Player_2", "point": "1200.0", "prize": {"value": 30}},
        {"rank": 3, "nickname": "Hero_3", "point": "1150.0", "prize": {"value": 20}},
        {"rank": 4, "nickname": "Player_4", "point": "1140.0", "prize": {"value": 10}},
    ]
    entries, hero_idx = build_player_entries(raw_players, "Hero_3")
    telemetry = calculate_hero_telemetry(entries, hero_idx, "Hero_3")

    assert telemetry.found is True
    assert telemetry.rank == 3
    assert telemetry.pts_to_next == 50.0  # 1200 - 1150
    assert telemetry.target_rank == 2
    assert telemetry.lead_over_prev == 10.0  # 1150 - 1140
    assert telemetry.trailing_rank == 4
    assert telemetry.cushion_danger is True  # lead < 20

def test_hero_rank_50_boundary_telemetry():
    raw_players = [{"rank": i, "nickname": f"P_{i}", "point": f"{1000 - i * 10}.0", "prize": {"value": 5}} for i in range(1, 51)]
    raw_players[49]["nickname"] = "Hero_50"

    entries, hero_idx = build_player_entries(raw_players, "Hero_50")
    telemetry = calculate_hero_telemetry(entries, hero_idx, "Hero_50")

    assert telemetry.found is True
    assert telemetry.rank == 50
    assert telemetry.target_rank == 49
    assert telemetry.lead_over_prev is None
    assert telemetry.trailing_rank == 51
    assert telemetry.cushion_danger is True

def test_hero_unranked_telemetry():
    raw_players = [{"rank": i, "nickname": f"P_{i}", "point": f"{1000 - i * 10}.0", "prize": {"value": 5}} for i in range(1, 51)]
    entries, hero_idx = build_player_entries(raw_players, "NotInTop50")
    telemetry = calculate_hero_telemetry(entries, hero_idx, "NotInTop50")

    assert telemetry.found is False
    assert telemetry.rank is None
    assert telemetry.target_rank == 50
    assert telemetry.pts_to_next == 500.0  # Rank 50 points
    assert telemetry.lead_over_prev is None

def test_hero_case_insensitive_and_whitespace():
    raw_players = [{"rank": 1, "nickname": "CaLoID", "point": "500.0", "prize": {"value": 10}}]
    entries, hero_idx = build_player_entries(raw_players, "   caloid   ")
    assert hero_idx == 0
    telemetry = calculate_hero_telemetry(entries, hero_idx, "   caloid   ")
    assert telemetry.found is True
    assert telemetry.rank == 1

def test_hero_empty_nickname_returns_none():
    raw_players = [{"rank": 1, "nickname": "CaLoID", "point": "500.0"}]
    entries, hero_idx = build_player_entries(raw_players, "")
    assert hero_idx is None
    telemetry = calculate_hero_telemetry(entries, hero_idx, "")
    assert telemetry is None

def test_hero_tied_points():
    raw_players = [
        {"rank": 1, "nickname": "Player_1", "point": "1000.0", "prize": {"value": 50}},
        {"rank": 2, "nickname": "TiedPlayer", "point": "800.0", "prize": {"value": 30}},
        {"rank": 3, "nickname": "Hero_Tied", "point": "800.0", "prize": {"value": 20}},
        {"rank": 4, "nickname": "Player_4", "point": "600.0", "prize": {"value": 10}},
    ]
    entries, hero_idx = build_player_entries(raw_players, "Hero_Tied")
    telemetry = calculate_hero_telemetry(entries, hero_idx, "Hero_Tied")
    assert telemetry.found is True
    assert telemetry.rank == 3
    assert telemetry.pts_to_next == 0.0  # Tied with rank 2
    assert telemetry.lead_over_prev == 200.0  # 800 - 600

def test_partial_table_unranked():
    # Only 10 players on high stake
    raw_players = [{"rank": i, "nickname": f"P_{i}", "point": f"{500 - i * 20}.0"} for i in range(1, 11)]
    entries, hero_idx = build_player_entries(raw_players, "Unknown")
    telemetry = calculate_hero_telemetry(entries, hero_idx, "Unknown")
    assert telemetry.found is False
    assert telemetry.target_rank == 10
    assert telemetry.pts_to_next == 300.0  # 500 - 10 * 20 = 300.0

def test_unpaid_player_null_prize_handling():
    raw_players = [
        {"rank": 1, "nickname": "Paid_1", "point": "1000.0", "prize": {"value": 50, "currencyId": "USD"}},
        {"rank": 2, "nickname": "Unpaid_2", "point": "500.0", "prize": None},
        {"rank": 3, "nickname": "Unpaid_3", "point": "200.0", "prize": {"value": 0}},
    ]
    entries, hero_idx = build_player_entries(raw_players, "Unpaid_2")
    assert entries[1].prize is None
    assert entries[1].prize_str == "-"
    telemetry = calculate_hero_telemetry(entries, hero_idx, "Unpaid_2")
    assert telemetry.prize is None
    assert telemetry.prize_value == 0.0
    assert telemetry.prize_diff_to_next == 50.0  # Paid_1 prize ($50) - 0
