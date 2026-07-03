"""
Automated tests for Phase 2: Job Ingestion.
Run with: pytest tests/test_phase2.py -v
"""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _unique_email():
    return f"test-{uuid.uuid4().hex[:8]}@example.com"


def _setup_queue():
    """Register a user and create org -> project -> queue, return (headers, queue_id)."""
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


def test_immediate_job_is_queued():
    headers, queue_id = _setup_queue()
    r = client.post(
        f"/api/v1/queues/{queue_id}/jobs", json={"type": "send_email", "payload": {"to": "a@b.com"}}, headers=headers
    )
    assert r.status_code == 201
    assert r.json()["status"] == "queued"


def test_delayed_job_is_scheduled():
    headers, queue_id = _setup_queue()
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    r = client.post(
        f"/api/v1/queues/{queue_id}/jobs", json={"type": "reminder", "payload": {}, "run_at": future}, headers=headers
    )
    assert r.status_code == 201
    assert r.json()["status"] == "scheduled"


def test_idempotency_key_prevents_duplicates():
    headers, queue_id = _setup_queue()
    body = {"type": "charge", "payload": {}, "idempotency_key": "order-1"}
    r1 = client.post(f"/api/v1/queues/{queue_id}/jobs", json=body, headers=headers)
    assert r1.status_code == 201
    r2 = client.post(f"/api/v1/queues/{queue_id}/jobs", json=body, headers=headers)
    assert r2.status_code == 409


def test_batch_job_creation_shares_batch_id():
    headers, queue_id = _setup_queue()
    r = client.post(
        f"/api/v1/queues/{queue_id}/jobs/batch",
        json={"jobs": [{"type": "resize", "payload": {"n": i}} for i in range(3)]},
        headers=headers,
    )
    assert r.status_code == 201
    jobs = r.json()
    assert len(jobs) == 3
    batch_ids = {j["batch_id"] for j in jobs}
    assert len(batch_ids) == 1


def test_recurring_job_valid_cron():
    headers, queue_id = _setup_queue()
    r = client.post(
        f"/api/v1/queues/{queue_id}/scheduled-jobs",
        json={"type": "daily_report", "payload_template": {}, "cron_expression": "0 9 * * *"},
        headers=headers,
    )
    assert r.status_code == 201
    assert r.json()["next_run_at"] is not None


def test_recurring_job_invalid_cron_rejected():
    headers, queue_id = _setup_queue()
    r = client.post(
        f"/api/v1/queues/{queue_id}/scheduled-jobs",
        json={"type": "bad", "payload_template": {}, "cron_expression": "not-a-cron"},
        headers=headers,
    )
    assert r.status_code == 422


def test_scheduled_job_requires_exactly_one_of_cron_or_run_once():
    headers, queue_id = _setup_queue()
    # neither
    r1 = client.post(
        f"/api/v1/queues/{queue_id}/scheduled-jobs", json={"type": "bad", "payload_template": {}}, headers=headers
    )
    assert r1.status_code == 422

    # both
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    r2 = client.post(
        f"/api/v1/queues/{queue_id}/scheduled-jobs",
        json={
            "type": "bad",
            "payload_template": {},
            "cron_expression": "0 9 * * *",
            "run_once_at": future,
        },
        headers=headers,
    )
    assert r2.status_code == 422


def test_paused_queue_rejects_new_jobs():
    headers, queue_id = _setup_queue()
    client.post(f"/api/v1/queues/{queue_id}/pause", headers=headers)
    r = client.post(f"/api/v1/queues/{queue_id}/jobs", json={"type": "x", "payload": {}}, headers=headers)
    assert r.status_code == 409


def test_job_status_filter():
    headers, queue_id = _setup_queue()
    client.post(f"/api/v1/queues/{queue_id}/jobs", json={"type": "a", "payload": {}}, headers=headers)
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    client.post(f"/api/v1/queues/{queue_id}/jobs", json={"type": "b", "payload": {}, "run_at": future}, headers=headers)

    r = client.get(f"/api/v1/queues/{queue_id}/jobs?status=scheduled", headers=headers)
    assert r.status_code == 200
    assert all(j["status"] == "scheduled" for j in r.json())
    assert len(r.json()) == 1


def test_cross_user_cannot_see_job():
    headers_a, queue_id = _setup_queue()
    r = client.post(f"/api/v1/queues/{queue_id}/jobs", json={"type": "x", "payload": {}}, headers=headers_a)
    job_id = r.json()["id"]

    headers_b, _ = _setup_queue()
    r_forbidden = client.get(f"/api/v1/jobs/{job_id}", headers=headers_b)
    assert r_forbidden.status_code == 403
