"""
Reaper — detects jobs stuck in 'claimed' or 'running' because their worker
died without cleaning up (e.g. SIGKILL, OOM-kill, host crash — anything that
skips the graceful-shutdown path in worker.py).

A job is considered stuck if its owning worker's last heartbeat is older than
--stale-after-seconds. Stuck jobs are requeued (or dead-lettered if retries
are exhausted) using the exact same retry policy logic as a normal failure,
so a crash counts as a failed attempt rather than a free pass.

Run continuously alongside the API and workers:
    python worker/reaper.py --interval 10 --stale-after-seconds 30
"""
import argparse
import logging
import sys
import time
import uuid

from sqlalchemy import create_engine, text

sys.path.insert(0, ".")
from app.core.config import settings
from app.core.retry import compute_retry_delay_seconds

logging.basicConfig(level=logging.INFO, format="%(asctime)s [REAPER] %(message)s")
logger = logging.getLogger("reaper")

FIND_STUCK_JOBS_SQL = text("""
    SELECT j.id, j.attempt_count, j.retry_policy_id, j.worker_id
    FROM jobs j
    JOIN workers w ON w.id = j.worker_id
    WHERE j.status IN ('claimed', 'running')
      AND (w.last_seen_at IS NULL OR w.last_seen_at < now() - (:stale_after || ' seconds')::interval)
    FOR UPDATE OF j SKIP LOCKED
""")

FIND_ORPHANED_JOBS_SQL = text("""
    -- Jobs claimed by a worker_id that no longer exists at all (defensive, shouldn't normally happen)
    SELECT j.id, j.attempt_count, j.retry_policy_id, j.worker_id
    FROM jobs j
    LEFT JOIN workers w ON w.id = j.worker_id
    WHERE j.status IN ('claimed', 'running') AND w.id IS NULL
    FOR UPDATE OF j SKIP LOCKED
""")

RETRY_POLICY_SQL = text(
    "SELECT strategy, base_delay_seconds, max_retries, max_delay_seconds FROM retry_policies WHERE id = :id"
)

DEFAULT_POLICY = {"strategy": "fixed", "base_delay_seconds": 5, "max_retries": 3, "max_delay_seconds": 3600}


class Reaper:
    def __init__(self, database_url: str, stale_after_seconds: int, interval: float):
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.stale_after_seconds = stale_after_seconds
        self.interval = interval

    def _get_policy(self, retry_policy_id):
        if retry_policy_id is None:
            return DEFAULT_POLICY
        with self.engine.connect() as conn:
            row = conn.execute(RETRY_POLICY_SQL, {"id": retry_policy_id}).mappings().first()
            return dict(row) if row else DEFAULT_POLICY

    def _reap_job(self, conn, job_id, attempt_count, retry_policy_id, mark_worker_offline_id=None):
        # The in-flight attempt never got to write back attempt_count, but it was
        # still a real, consumed attempt (the worker crashed mid-run) — count it,
        # exactly like a normal failure does in worker.py's _handle_failure.
        attempt_number = attempt_count + 1
        policy = self._get_policy(retry_policy_id)

        # mark the abandoned execution row (if one is still 'running') as failed
        conn.execute(
            text(
                "UPDATE job_executions SET status = 'failed', finished_at = now(), "
                "error_message = 'Worker heartbeat timeout - presumed crashed' "
                "WHERE job_id = :job_id AND status = 'running'"
            ),
            {"job_id": job_id},
        )

        if attempt_number < policy["max_retries"]:
            delay = compute_retry_delay_seconds(
                policy["strategy"], attempt_number, policy["base_delay_seconds"], policy["max_delay_seconds"]
            )
            conn.execute(
                text(
                    "UPDATE jobs SET status = 'scheduled', attempt_count = :n, "
                    "run_at = now() + (:delay || ' seconds')::interval, "
                    "worker_id = NULL, claimed_at = NULL, updated_at = now() WHERE id = :id"
                ),
                {"n": attempt_number, "delay": delay, "id": job_id},
            )
            logger.warning(f"Job {job_id}: worker presumed dead — requeued (attempt {attempt_number}, +{delay:.1f}s)")
        else:
            conn.execute(
                text("UPDATE jobs SET status = 'dead_letter', attempt_count = :n, updated_at = now() WHERE id = :id"),
                {"n": attempt_number, "id": job_id},
            )
            conn.execute(
                text(
                    "INSERT INTO dead_letter_queue (id, job_id, final_error, attempt_count, moved_at, resolved) "
                    "VALUES (:id, :job_id, 'Worker heartbeat timeout - retries exhausted', :n, now(), false)"
                ),
                {"id": uuid.uuid4(), "job_id": job_id, "n": attempt_number},
            )
            logger.error(f"Job {job_id}: worker presumed dead — retries exhausted, moved to DLQ")

    def sweep_stuck_workers(self, conn):
        """Mark workers whose heartbeat has gone stale as offline (visibility for the dashboard)."""
        result = conn.execute(
            text(
                "UPDATE workers SET status = 'offline' "
                "WHERE status = 'online' AND (last_seen_at IS NULL OR last_seen_at < now() - (:stale || ' seconds')::interval) "
                "RETURNING id"
            ),
            {"stale": self.stale_after_seconds},
        )
        stale_workers = [r[0] for r in result.fetchall()]
        for wid in stale_workers:
            logger.warning(f"Worker {wid} marked offline (heartbeat stale > {self.stale_after_seconds}s)")

    def run_once(self):
        with self.engine.begin() as conn:
            self.sweep_stuck_workers(conn)

            stuck = conn.execute(FIND_STUCK_JOBS_SQL, {"stale_after": self.stale_after_seconds}).fetchall()
            for row in stuck:
                self._reap_job(conn, row.id, row.attempt_count, row.retry_policy_id)

            orphaned = conn.execute(FIND_ORPHANED_JOBS_SQL).fetchall()
            for row in orphaned:
                self._reap_job(conn, row.id, row.attempt_count, row.retry_policy_id)

            if stuck or orphaned:
                logger.info(f"Reaped {len(stuck) + len(orphaned)} stuck job(s)")

    def run_forever(self):
        logger.info(f"Reaper started (stale_after={self.stale_after_seconds}s, interval={self.interval}s)")
        while True:
            try:
                self.run_once()
            except Exception:
                logger.exception("Reaper sweep failed, will retry next interval")
            time.sleep(self.interval)


def main():
    parser = argparse.ArgumentParser(description="Reaper: detects and recovers stuck/zombie jobs")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--stale-after-seconds", type=int, default=30)
    parser.add_argument("--interval", type=float, default=10.0)
    args = parser.parse_args()

    database_url = args.database_url or settings.DATABASE_URL
    Reaper(database_url, args.stale_after_seconds, args.interval).run_forever()


if __name__ == "__main__":
    main()
