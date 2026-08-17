import os
import sys
from pathlib import Path

os.environ.setdefault("CLOUD_DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("CLOUD_JWT_SECRET", "test-secret-that-is-long-enough-for-hs256")
os.environ.setdefault(
    "CLOUD_API_KEY_PEPPER", "test-pepper-that-is-long-enough-for-hs256"
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from app.db import get_db
from app.main import app
from app.models import Base
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def account(client):
    """A signed-up owner with one vehicle and an enrolled agent."""

    def _make(email="owner@example.com"):
        token = client.post(
            "/v1/auth/signup",
            json={
                "email": email,
                "password": "correct-horse-battery",
                "org_name": "Garage",
            },
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        vehicle_id = client.post(
            "/v1/vehicles", json={"name": "Ioniq 5"}, headers=headers
        ).json()["id"]
        code = client.post(
            f"/v1/vehicles/{vehicle_id}/enrollment-codes", headers=headers
        ).json()["code"]
        api_key = client.post(
            "/v1/agents/enroll", json={"code": code, "agent_name": "pi"}
        ).json()["api_key"]
        return {
            "headers": headers,
            "vehicle_id": vehicle_id,
            "api_key": api_key,
            "agent_headers": {"Authorization": f"Bearer {api_key}"},
        }

    return _make
