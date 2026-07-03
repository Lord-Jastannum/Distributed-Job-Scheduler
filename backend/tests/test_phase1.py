"""
Automated tests for Phase 1: Auth + Organizations/Projects/Queues CRUD.
Run with: pytest tests/test_phase1.py -v
Requires a running Postgres instance matching DATABASE_URL in app/core/config.py.
"""
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _unique_email():
    return f"test-{uuid.uuid4().hex[:8]}@example.com"


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_register_and_login():
    email = _unique_email()
    r = client.post("/api/v1/auth/register", json={"email": email, "password": "testpass123", "name": "Test User"})
    assert r.status_code == 201
    assert r.json()["email"] == email

    # duplicate registration should fail
    r2 = client.post("/api/v1/auth/register", json={"email": email, "password": "testpass123", "name": "Test User"})
    assert r2.status_code == 409

    # login
    r3 = client.post("/api/v1/auth/login", data={"username": email, "password": "testpass123"})
    assert r3.status_code == 200
    assert "access_token" in r3.json()

    # wrong password
    r4 = client.post("/api/v1/auth/login", data={"username": email, "password": "wrong"})
    assert r4.status_code == 401


def _auth_headers():
    email = _unique_email()
    client.post("/api/v1/auth/register", json={"email": email, "password": "testpass123", "name": "Test User"})
    r = client.post("/api/v1/auth/login", data={"username": email, "password": "testpass123"})
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_unauthenticated_access_rejected():
    r = client.get("/api/v1/organizations")
    assert r.status_code == 401


def test_org_project_queue_chain():
    headers = _auth_headers()

    r = client.post("/api/v1/organizations", json={"name": "Test Org"}, headers=headers)
    assert r.status_code == 201
    org_id = r.json()["id"]

    r = client.post(f"/api/v1/organizations/{org_id}/projects", json={"name": "Test Project"}, headers=headers)
    assert r.status_code == 201
    project_id = r.json()["id"]

    r = client.post(
        f"/api/v1/projects/{project_id}/queues",
        json={"name": "test-queue", "priority": 1, "concurrency_limit": 3},
        headers=headers,
    )
    assert r.status_code == 201
    queue_id = r.json()["id"]
    assert r.json()["status"] == "active"

    # duplicate queue name in same project
    r_dup = client.post(
        f"/api/v1/projects/{project_id}/queues",
        json={"name": "test-queue", "priority": 1, "concurrency_limit": 3},
        headers=headers,
    )
    assert r_dup.status_code == 409

    # pause / resume
    r_pause = client.post(f"/api/v1/queues/{queue_id}/pause", headers=headers)
    assert r_pause.json()["status"] == "paused"

    r_resume = client.post(f"/api/v1/queues/{queue_id}/resume", headers=headers)
    assert r_resume.json()["status"] == "active"


def test_cross_user_isolation():
    headers_a = _auth_headers()
    headers_b = _auth_headers()

    r = client.post("/api/v1/organizations", json={"name": "User A Org"}, headers=headers_a)
    org_id = r.json()["id"]

    # user B must not be able to see user A's org
    r_forbidden = client.get(f"/api/v1/organizations/{org_id}", headers=headers_b)
    assert r_forbidden.status_code == 403


def test_validation_errors():
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "short", "name": ""},
    )
    assert r.status_code == 422
    assert "error" in r.json()
