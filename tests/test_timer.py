import pytest
from datetime import datetime, timezone, timedelta
from app.telemetry import compute_cutoff

def test_cutoff_morning_before_reset():
    # 06:30:00 UTC -> 1.5 hours (5400s) until 08:00:00 UTC
    now_utc = datetime(2026, 10, 13, 6, 30, 0, tzinfo=timezone.utc)
    cutoff_dt, secs, formatted = compute_cutoff(now=now_utc)
    assert cutoff_dt == datetime(2026, 10, 13, 8, 0, 0, tzinfo=timezone.utc)
    assert secs == 5400
    assert formatted == "01ч 30м 00с"

def test_cutoff_afternoon_after_reset():
    # 14:00:00 UTC -> 18 hours (64800s) until tomorrow 08:00:00 UTC
    now_utc = datetime(2026, 10, 13, 14, 0, 0, tzinfo=timezone.utc)
    cutoff_dt, secs, formatted = compute_cutoff(now=now_utc)
    assert cutoff_dt == datetime(2026, 10, 14, 8, 0, 0, tzinfo=timezone.utc)
    assert secs == 64800
    assert formatted == "18ч 00м 00с"

def test_cutoff_exact_boundary():
    # Exactly 08:00:00 UTC -> 24 hours (86400s)
    now_utc = datetime(2026, 10, 13, 8, 0, 0, tzinfo=timezone.utc)
    cutoff_dt, secs, formatted = compute_cutoff(now=now_utc)
    assert cutoff_dt == datetime(2026, 10, 14, 8, 0, 0, tzinfo=timezone.utc)
    assert secs == 86400
    assert formatted == "24ч 00м 00с"

def test_cutoff_custom_finished_at_in_future():
    now_utc = datetime(2026, 10, 13, 7, 0, 0, tzinfo=timezone.utc)
    custom_fin = "2026-10-13T07:45:00+00:00"
    cutoff_dt, secs, formatted = compute_cutoff(finished_at=custom_fin, now=now_utc)
    assert secs == 2700  # 45 minutes
    assert formatted == "00ч 45м 00с"

def test_cutoff_custom_finished_at_in_past_falls_back():
    now_utc = datetime(2026, 10, 13, 9, 0, 0, tzinfo=timezone.utc)
    past_fin = "2026-10-13T08:00:00+00:00"
    cutoff_dt, secs, formatted = compute_cutoff(finished_at=past_fin, now=now_utc)
    assert cutoff_dt == datetime(2026, 10, 14, 8, 0, 0, tzinfo=timezone.utc)
    assert secs == 23 * 3600

def test_cutoff_non_utc_timezone_awareness_msk():
    # UTC+3 MSK: 10:30:00 MSK == 07:30:00 UTC -> 30 mins (1800s) to 08:00:00 UTC
    tz_msk = timezone(timedelta(hours=3))
    t_msk = datetime(2026, 10, 13, 10, 30, 0, tzinfo=tz_msk)
    cutoff_dt, secs, formatted = compute_cutoff(now=t_msk)
    assert cutoff_dt == datetime(2026, 10, 13, 8, 0, 0, tzinfo=timezone.utc)
    assert secs == 1800
    assert formatted == "00ч 30м 00с"
    assert cutoff_dt.tzinfo == timezone.utc

def test_cutoff_non_utc_timezone_awareness_est():
    # UTC-5 EST: 01:00:00 EST == 06:00:00 UTC -> 2 hours (7200s) to 08:00:00 UTC
    tz_est = timezone(timedelta(hours=-5))
    t_est = datetime(2026, 10, 13, 1, 0, 0, tzinfo=tz_est)
    cutoff_dt, secs, formatted = compute_cutoff(now=t_est)
    assert cutoff_dt == datetime(2026, 10, 13, 8, 0, 0, tzinfo=timezone.utc)
    assert secs == 7200
    assert formatted == "02ч 00м 00с"
    assert cutoff_dt.tzinfo == timezone.utc

def test_cutoff_non_utc_timezone_awareness_jst_after_reset():
    # UTC+9 JST: 18:00:00 JST == 09:00:00 UTC -> 23 hours (82800s) to next day 08:00:00 UTC
    tz_jst = timezone(timedelta(hours=9))
    t_jst = datetime(2026, 10, 13, 18, 0, 0, tzinfo=tz_jst)
    cutoff_dt, secs, formatted = compute_cutoff(now=t_jst)
    assert cutoff_dt == datetime(2026, 10, 14, 8, 0, 0, tzinfo=timezone.utc)
    assert secs == 82800
    assert formatted == "23ч 00м 00с"
    assert cutoff_dt.tzinfo == timezone.utc

def test_cutoff_naive_datetime_assumes_utc():
    # Naive datetime: 07:15:00 naive -> treated as UTC -> 45 mins (2700s)
    t_naive = datetime(2026, 10, 13, 7, 15, 0)
    cutoff_dt, secs, formatted = compute_cutoff(now=t_naive)
    assert cutoff_dt == datetime(2026, 10, 13, 8, 0, 0, tzinfo=timezone.utc)
    assert secs == 2700
    assert formatted == "00ч 45м 00с"
    assert cutoff_dt.tzinfo == timezone.utc

def test_cutoff_custom_finished_at_non_utc():
    now_utc = datetime(2026, 10, 13, 7, 0, 0, tzinfo=timezone.utc)
    # 10:45:00 UTC+3 == 07:45:00 UTC -> 45 mins (2700s)
    custom_fin_msk = "2026-10-13T10:45:00+03:00"
    cutoff_dt, secs, formatted = compute_cutoff(finished_at=custom_fin_msk, now=now_utc)
    assert cutoff_dt == datetime(2026, 10, 13, 7, 45, 0, tzinfo=timezone.utc)
    assert secs == 2700
    assert formatted == "00ч 45м 00с"
    assert cutoff_dt.tzinfo == timezone.utc

