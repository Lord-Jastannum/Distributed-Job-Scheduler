"""
Automated tests for Phase 6 bonus features.
WebSocket live updates is covered by manual browser testing in the Phase 6
handoff (harder to meaningfully assert on inside pytest without a running
event loop client); this file covers workflow dependencies and rate limiting,
which are both fully testable via TestClient.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _unique_email():
    return f"test-{uuid.uuid4().hex[:8]}@example.com"


def _setup_queue():
    email = _unique_email()
    client.post("/api/v1/auth/register", json={"email": email, "password": "testpass123", "name": "Test User"})
    r = client.post("/api/v1/auth/login", data={"username": email, "password": "testpass123"})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    org_id = client.post("/api/v1/organizations", json={"name": "Org"}, headers=headers).json()["id"]
    project_id = client.post(
        f"/api/v1/organizations/{org_id}/projects", json={"name": "Project"}, headers=headers
    ).json()["id"]
    queue_id = client.post(
        f"/api/v1/projects/{project_id}/queues",
        json={"name": "queue", "priority": 0, "concurrency_limit": 5},
        headers=headers,
    ).json()["id"]
    return headers, queue_id


def test_job_can_declare_a_dependency():
    headers, queue_id = _setup_queue()
    job_a = client.post(f"/api/v1/queues/{queue_id}/jobs", json={"type": "a", "payload": {}}, headers=headers).json()

    r = client.post(
        f"/api/v1/queues/{queue_id}/jobs",
        json={"type": "b", "payload": {}, "depends_on_job_id": job_a["id"]},
        headers=headers,
    )
    assert r.status_code == 201
    assert r.json()["depends_on_job_id"] == job_a["id"]


def test_dependency_must_exist_in_same_queue():
    headers, queue_id = _setup_queue()
    fake_dependency = uuid.uuid4()
    r = client.post(
        f"/api/v1/queues/{queue_id}/jobs",
        json={"type": "b", "payload": {}, "depends_on_job_id": str(fake_dependency)},
        headers=headers,
    )
    assert r.status_code == 422


def test_dependency_must_be_in_same_queue_not_another_queue():
    headers, queue_id_a = _setup_queue()

    # a second queue for the SAME user (same org/project chain), so this test
    # isolates the cross-queue dependency check from unrelated ownership checks
    email = _unique_email()
    orgs = client.get("/api/v1/organizations", headers=headers).json()
    org_id = orgs[0]["id"]
    projects = client.get(f"/api/v1/organizations/{org_id}/projects", headers=headers).json()
    project_id = projects[0]["id"]
    queue_id_b = client.post(
        f"/api/v1/projects/{project_id}/queues",
        json={"name": "second-queue", "priority": 0, "concurrency_limit": 5},
        headers=headers,
    ).json()["id"]

    job_in_a = client.post(
        f"/api/v1/queues/{queue_id_a}/jobs", json={"type": "a", "payload": {}}, headers=headers
    ).json()

    # attempting to depend on a job from a different queue should be rejected
    r = client.post(
        f"/api/v1/queues/{queue_id_b}/jobs",
        json={"type": "b", "payload": {}, "depends_on_job_id": job_in_a["id"]},
        headers=headers,
    )
    assert r.status_code == 422


def test_claim_sql_skips_job_with_incomplete_dependency():
    """This exercises the actual claim SQL used by worker.py directly against
    the DB, proving the dependency gate works at the SQL level (not just that
    the API stores the field)."""
    from sqlalchemy import create_engine, text
    from app.core.config import settings
    from worker.worker import CLAIM_SQL

    headers, queue_id = _setup_queue()
    job_a = client.post(f"/api/v1/queues/{queue_id}/jobs", json={"type": "a", "payload": {}}, headers=headers).json()
    job_b = client.post(
        f"/api/v1/queues/{queue_id}/jobs",
        json={"type": "b", "payload": {}, "depends_on_job_id": job_a["id"]},
        headers=headers,
    ).json()

    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        worker_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO workers (id, project_id, hostname, status) "
                "VALUES (:id, (SELECT project_id FROM queues WHERE id = :qid), 'test', 'online')"
            ),
            {"id": worker_id, "qid": queue_id},
        )
        conn.commit()

        # Claim everything claimable right now - job_a should come back, job_b should NOT
        # (its dependency, job_a, hasn't completed yet)
        claimed = conn.execute(
            CLAIM_SQL, {"worker_id": worker_id, "queue_id": queue_id, "batch_size": 10}
        ).fetchall()
        conn.commit()
        claimed_ids = {str(row.id) for row in claimed}

        assert job_a["id"] in claimed_ids
        assert job_b["id"] not in claimed_ids

        # Now complete job_a and confirm job_b becomes claimable
        conn.execute(text("UPDATE jobs SET status = 'completed' WHERE id = :id"), {"id": job_a["id"]})
        conn.commit()

        claimed_round_2 = conn.execute(
            CLAIM_SQL, {"worker_id": worker_id, "queue_id": queue_id, "batch_size": 10}
        ).fetchall()
        conn.commit()
        claimed_ids_2 = {str(row.id) for row in claimed_round_2}
        assert job_b["id"] in claimed_ids_2


def test_rate_limiting_blocks_excessive_login_attempts():
    """Re-enables the limiter just for this test (globally disabled by conftest.py)
    to prove it actually fires, rather than just trusting the decorator is present."""
    app.state.limiter.enabled = True
    try:
        email = _unique_email()
        client.post("/api/v1/auth/register", json={"email": email, "password": "testpass123", "name": "Test"})

        responses = [
            client.post("/api/v1/auth/login", data={"username": email, "password": "wrong"})
            for _ in range(15)
        ]
        statuses = [r.status_code for r in responses]
        assert 429 in statuses, f"Expected a 429 among 15 rapid login attempts, got: {statuses}"
    finally:
        app.state.limiter.enabled = False
