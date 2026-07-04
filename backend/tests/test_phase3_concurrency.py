"""
Automated test for Phase 3: proves the atomic claim SQL is race-free.

This runs two real concurrent database sessions (via threads) against the same
set of queued jobs, both executing the exact CLAIM_SQL used by worker.py, and
asserts that no job is ever claimed by both. This is the automated version of
the manual stress test described in the Phase 3 handoff (60 jobs, 3 worker
processes, 0 duplicates).
"""
import threading
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text

from app.core.config import settings
from worker.worker import CLAIM_SQL


@pytest.fixture
def engine():
    return create_engine(settings.DATABASE_URL)


def _setup_test_data(engine):
    """Creates a user/org/project/queue and N queued jobs via raw SQL, returns queue_id."""
    with engine.connect() as conn:
        user_id = uuid.uuid4()
        org_id = uuid.uuid4()
        project_id = uuid.uuid4()
        queue_id = uuid.uuid4()

        conn.execute(
            text("INSERT INTO users (id, email, password_hash, name) VALUES (:id, :email, 'x', 'Test')"),
            {"id": user_id, "email": f"concurrency-{uuid.uuid4().hex[:8]}@test.com"},
        )
        conn.execute(
            text("INSERT INTO organizations (id, name, owner_id) VALUES (:id, 'org', :owner_id)"),
            {"id": org_id, "owner_id": user_id},
        )
        conn.execute(
            text("INSERT INTO projects (id, organization_id, name) VALUES (:id, :org_id, 'proj')"),
            {"id": project_id, "org_id": org_id},
        )
        conn.execute(
            text(
                "INSERT INTO queues (id, project_id, name, priority, concurrency_limit, status) "
                "VALUES (:id, :project_id, 'q', 0, 5, 'active')"
            ),
            {"id": queue_id, "project_id": project_id},
        )
        for _ in range(40):
            conn.execute(
                text(
                    "INSERT INTO jobs (id, queue_id, type, payload, status, priority, run_at, attempt_count) "
                    "VALUES (:id, :queue_id, 'test', '{}', 'queued', 0, now(), 0)"
                ),
                {"id": uuid.uuid4(), "queue_id": queue_id},
            )
        conn.commit()
        return queue_id


def test_concurrent_claims_never_overlap(engine):
    queue_id = _setup_test_data(engine)

    claimed_by_thread_a = []
    claimed_by_thread_b = []

    def claim_worker(worker_id: uuid.UUID, result_list: list, batch_size: int):
        with engine.connect() as conn:
            rows = conn.execute(
                CLAIM_SQL, {"worker_id": worker_id, "queue_id": queue_id, "batch_size": batch_size}
            ).fetchall()
            conn.commit()
            result_list.extend([r[0] for r in rows])

    worker_a_id = uuid.uuid4()
    worker_b_id = uuid.uuid4()

    with engine.connect() as conn:
        for wid in (worker_a_id, worker_b_id):
            conn.execute(
                text(
                    "INSERT INTO workers (id, project_id, hostname, status) "
                    "VALUES (:id, (SELECT project_id FROM queues WHERE id = :queue_id), 'test-host', 'online')"
                ),
                {"id": wid, "queue_id": queue_id},
            )
        conn.commit()

    thread_a = threading.Thread(target=claim_worker, args=(worker_a_id, claimed_by_thread_a, 25))
    thread_b = threading.Thread(target=claim_worker, args=(worker_b_id, claimed_by_thread_b, 25))

    thread_a.start()
    thread_b.start()
    thread_a.join()
    thread_b.join()

    set_a = set(claimed_by_thread_a)
    set_b = set(claimed_by_thread_b)

    # The core assertion: zero overlap between what two concurrent claimers got
    assert set_a.isdisjoint(set_b), f"Jobs claimed by both threads: {set_a & set_b}"

    # And together they should have claimed exactly all 40 jobs (no job left behind, none double-counted)
    assert len(set_a) + len(set_b) == 40
