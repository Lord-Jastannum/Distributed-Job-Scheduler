"""
Automated tests for Phase 4: retry backoff math and DLQ REST endpoints.
The worker's actual retry-on-failure and reaper crash-recovery behavior is
covered by the manual test log in the Phase 4 handoff (retry -> DLQ, and
repeated-crash -> DLQ via the reaper) since it requires real subprocess
workers and SIGKILL, which isn't practical inside pytest.
"""
import uuid

from fastapi.testclient import TestClient

from app.core.retry import compute_retry_delay_seconds
from app.main import app

client = TestClient(app)


def test_fixed_strategy_delay_is_constant():
    d1 = compute_retry_delay_seconds("fixed", 1, base_delay=10, max_delay=3600)
    d2 = compute_retry_delay_seconds("fixed", 5, base_delay=10, max_delay=3600)
    # both should be ~10s plus up to 10% jitter, i.e. in [10, 11]
    assert 10 <= d1 <= 11
    assert 10 <= d2 <= 11


def test_linear_strategy_delay_grows_linearly():
    d1 = compute_retry_delay_seconds("linear", 1, base_delay=5, max_delay=3600)
    d3 = compute_retry_delay_seconds("linear", 3, base_delay=5, max_delay=3600)
    assert 5 <= d1 <= 5.5
    assert 15 <= d3 <= 16.5


def test_exponential_strategy_delay_doubles():
    d1 = compute_retry_delay_seconds("exponential", 1, base_delay=2, max_delay=3600)
    d2 = compute_retry_delay_seconds("exponential", 2, base_delay=2, max_delay=3600)
    d3 = compute_retry_delay_seconds("exponential", 3, base_delay=2, max_delay=3600)
    assert 2 <= d1 <= 2.2
    assert 4 <= d2 <= 4.4
    assert 8 <= d3 <= 8.8


def test_exponential_strategy_respects_max_delay_cap():
    d = compute_retry_delay_seconds("exponential", 20, base_delay=5, max_delay=60)
    assert d <= 66  # 60 + 10% jitter ceiling


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


def test_dlq_list_empty_when_no_failures():
    headers, queue_id = _setup_queue()
    r = client.get(f"/api/v1/queues/{queue_id}/dead-letter-queue", headers=headers)
    assert r.status_code == 200
    assert r.json() == []


def test_dlq_replay_and_dismiss_endpoints_404_on_unknown_id():
    headers, _ = _setup_queue()
    fake_id = uuid.uuid4()
    r1 = client.post(f"/api/v1/dead-letter-queue/{fake_id}/replay", headers=headers)
    assert r1.status_code == 404
    r2 = client.post(f"/api/v1/dead-letter-queue/{fake_id}/dismiss", headers=headers)
    assert r2.status_code == 404
