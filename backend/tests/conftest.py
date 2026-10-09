import os
import sys
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ["SECRET_KEY"] = "test" * 10
os.environ["SEED_DEMO_DATA"] = "1"
os.environ["ADMIN_PASSWORD"] = "adminpass"
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def auth(client):
    r = client.post("/api/auth/login", data={"username": "admin", "password": "adminpass"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
