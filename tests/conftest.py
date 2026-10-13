import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import get_settings

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def auth_headers(client):
    pin = get_settings().pin
    res = client.post("/api/auth", json={"pin": pin})
    token = res.json()["token"]
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def sample_rankings():
    return [
        {"rank": 1, "nickname": "LeaderAlpha", "point": "2500.0", "prize": {"value": 50, "prizeItem": [{"type": "TICKET", "quantity": 10, "value": 5}]}},
        {"rank": 2, "nickname": "ChaserBeta", "point": "2300.0", "prize": {"value": 30, "prizeItem": [{"type": "TICKET", "quantity": 6, "value": 5}]}},
        {"rank": 3, "nickname": "GrinderGamma", "point": "2100.0", "prize": {"value": 20, "prizeItem": [{"type": "TICKET", "quantity": 4, "value": 5}]}},
        {"rank": 4, "nickname": "TiedDelta1", "point": "1900.0", "prize": {"value": 15, "prizeItem": [{"type": "TICKET", "quantity": 3, "value": 5}]}},
        {"rank": 5, "nickname": "TiedDelta2", "point": "1900.0", "prize": {"value": 10, "prizeItem": [{"type": "TICKET", "quantity": 2, "value": 5}]}},
    ]
