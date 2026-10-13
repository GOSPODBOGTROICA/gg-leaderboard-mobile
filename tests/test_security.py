import os
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import get_settings
from app.auth import verify_pin, create_session_token, is_valid_token

@pytest.fixture
def client():
    return TestClient(app)

def test_pin_verification_default():
    # Default is 7777 unless overridden
    assert verify_pin("7777") is True
    assert verify_pin("0000") is False
    assert verify_pin("") is False

def test_pin_env_override(monkeypatch):
    monkeypatch.setenv("APP_PIN", "9999")
    assert get_settings().pin == "9999"
    assert verify_pin("9999") is True
    assert verify_pin("7777") is False

def test_auth_endpoint_bad_pin(client):
    res = client.post("/api/auth", json={"pin": "wrong_pin"})
    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid PIN"

def test_auth_endpoint_good_pin(client):
    # Use whatever PIN is currently active
    active_pin = get_settings().pin
    res = client.post("/api/auth", json={"pin": active_pin})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "token" in data
    assert len(data["token"]) == 64
    assert data["expires_in"] > 0
    # Cookie should also be set
    assert "session_token" in res.cookies

def test_protected_endpoints_401_without_auth(client):
    r1 = client.get("/api/stakes")
    assert r1.status_code == 401
    assert r1.json()["detail"] == "Unauthorized"

    r2 = client.get("/api/leaderboard?stake=$1")
    assert r2.status_code == 401
    assert r2.json()["detail"] == "Unauthorized"

def test_protected_endpoints_200_with_bearer_token(client):
    active_pin = get_settings().pin
    auth_res = client.post("/api/auth", json={"pin": active_pin})
    token = auth_res.json()["token"]

    headers = {"Authorization": f"Bearer {token}"}
    r = client.get("/api/stakes", headers=headers)
    assert r.status_code == 200
    assert "stakes" in r.json()

def test_protected_endpoints_200_with_cookie(client):
    active_pin = get_settings().pin
    auth_res = client.post("/api/auth", json={"pin": active_pin})
    token = auth_res.json()["token"]

    client_with_cookie = TestClient(app, cookies={"session_token": token})
    r = client_with_cookie.get("/api/stakes")
    assert r.status_code == 200
    assert "stakes" in r.json()
