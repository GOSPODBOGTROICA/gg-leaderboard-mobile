import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import get_settings

client = TestClient(app)

@pytest.fixture
def auth_headers():
    pin = get_settings().pin
    res = client.post("/api/auth", json={"pin": pin})
    token = res.json()["token"]
    return {"Authorization": f"Bearer {token}"}

def test_health_check():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["app"] == "GG_LEADERBOARD_MOBILE"

def test_get_stakes_authenticated(auth_headers):
    res = client.get("/api/stakes", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "group_id" in data
    assert "cutoff_utc" in data
    assert "stakes" in data
    assert len(data["stakes"]) == 9
    stake_names = [s["stake"] for s in data["stakes"]]
    assert "$0.25" in stake_names
    assert "$1" in stake_names
    assert "$200" in stake_names

def test_get_leaderboard_authenticated(auth_headers):
    res = client.get("/api/leaderboard?stake=$1", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["stake"] == "$1"
    assert "cutoff_seconds" in data
    assert "players" in data
    assert len(data["players"]) > 0
    # Rank 1 checks
    p1 = data["players"][0]
    assert p1["rank"] == 1
    assert "nickname" in p1
    assert "points" in p1
    assert isinstance(p1["points"], float)

def test_get_leaderboard_with_hero(auth_headers):
    # Fetch leaderboard to get real nickname
    res = client.get("/api/leaderboard?stake=$1", headers=auth_headers)
    assert res.status_code == 200
    p1_nick = res.json()["players"][0]["nickname"]

    # Now query with hero
    res_hero = client.get(f"/api/leaderboard?stake=$1&hero={p1_nick}", headers=auth_headers)
    assert res_hero.status_code == 200
    data = res_hero.json()
    assert data["hero"] is not None
    assert data["hero"]["found"] is True
    assert data["hero"]["rank"] == 1
    assert data["hero"]["pts_to_next"] == 0.0

def test_unsupported_stake_returns_400(auth_headers):
    res = client.get("/api/leaderboard?stake=$999", headers=auth_headers)
    assert res.status_code == 400
    assert "Missing or unsupported stake parameter" in res.json()["detail"]

def test_caching_behavior(auth_headers):
    # First call might be fresh
    client.get("/api/leaderboard?stake=$1", headers=auth_headers)
    # Immediate second call must be cached
    res2 = client.get("/api/leaderboard?stake=$1", headers=auth_headers)
    assert res2.status_code == 200
    assert res2.json()["cached"] is True
