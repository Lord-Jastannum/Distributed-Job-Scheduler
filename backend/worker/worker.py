"""
Distributed Job Scheduler — Worker Process

Polls a queue, atomically claims jobs using `SELECT ... FOR UPDATE SKIP LOCKED`,
executes them concurrently up to the queue's concurrency_limit, sends periodic
heartbeats, and shuts down gracefully on SIGINT/SIGTERM (finishes in-flight jobs
before exiting rather than dying mid-job).

Usage:
    python worker/worker.py --queue-id <uuid> --project-id <uuid>

This process talks directly to Postgres rather than through the REST API.
See the Phase 0 architecture doc, section 4, for why: the claim loop is the
hottest path in the whole system, and routing it through HTTP+auth for every
poll adds latency and load with no correctness benefit — the atomicity comes
from the SQL, not from the API layer.
"""
import argparse
import logging
import signal
import socket
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, Future
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] worker=%(worker_short)s %(message)s",
)


class WorkerIdFilter(logging.Filter):
    """Injects a short worker id into every log line so multi-worker output is readable."""

    def __init__(self, worker_id: uuid.UUID):
        super().__init__()
        self.worker_short = str(worker_id)[:8]

    def filter(self, record):
        record.worker_short = self.worker_short
        return True


# --- Dummy job handlers -----------------------------------------------------
# In a real system these would dispatch to actual business logic based on job.type.
# For this assignment, handlers simulate work and can simulate failure via payload.

def run_handler(job_type: str, payload: dict) -> None:
    duration = payload.get("_simulate_duration_seconds", 0.5)
    time.sleep(duration)
    if payload.get("_simulate_failure"):
        raise RuntimeError(f"Simulated failure for job type '{job_type}'")


# --- Claim SQL ---------------------------------------------------------------
# The core atomicity mechanism: FOR UPDATE SKIP LOCKED means concurrent workers
# never block on each other and never claim the same row twice. See the
# architecture doc (Phase 0, section 4) for the full reasoning.
CLAIM_SQL = text("""
    UPDATE jobs
    SET status = 'claimed', worker_id = :worker_id, claimed_at = now(), updated_at = now()
    WHERE id IN (
        SELECT id FROM jobs
        WHERE queue_id = :queue_id
          AND status IN ('queued', 'scheduled')
          AND run_at <= now()
        ORDER BY priority DESC, run_at ASC
        FOR UPDATE SKIP LOCKED
        LIMIT :batch_size
    )
    RETURNING id, type, payload, attempt_count;
""")


class Worker:
    def __init__(
        self,
        database_url: str,
        project_id: uuid.UUID,
        queue_id: uuid.UUID,
        concurrency: int,
        poll_interval: float = 2.0,
        heartbeat_interval: float = 5.0,
    ):
        self.engine = create_engine(database_url, pool_pre_ping=True, pool_size=concurrency + 5)
        self.Session = sessionmaker(bind=self.engine)
        self.project_id = project_id
        self.queue_id = queue_id
        self.concurrency = concurrency
        self.poll_interval = poll_interval
        self.heartbeat_interval = heartbeat_interval

        self.id = uuid.uuid4()
        self.hostname = socket.gethostname()

        self.logger = logging.getLogger(f"worker.{self.id}")
        self.logger.addFilter(WorkerIdFilter(self.id))

        self._shutdown = False
        self._active_jobs = 0
        self._executor = ThreadPoolExecutor(max_workers=concurrency)
        self._in_flight: list[Future] = []

    # -- lifecycle -----------------------------------------------------------

    def register(self):
        with self.Session() as session:
            session.execute(
                text(
                    "INSERT INTO workers (id, project_id, hostname, status, registered_at, last_seen_at) "
                    "VALUES (:id, :project_id, :hostname, 'online', now(), now())"
                ),
                {"id": self.id, "project_id": self.project_id, "hostname": self.hostname},
            )
            session.commit()
        self.logger.info(f"Registered worker {self.id} ({self.hostname}) for queue {self.queue_id}")

    def deregister(self, final_status: str = "offline"):
        with self.Session() as session:
            session.execute(
                text("UPDATE workers SET status = :status, last_seen_at = now() WHERE id = :id"),
                {"status": final_status, "id": self.id},
            )
            session.commit()
        self.logger.info(f"Worker marked {final_status}")

    def send_heartbeat(self):
        with self.Session() as session:
            session.execute(
                text(
                    "INSERT INTO worker_heartbeats (worker_id, sent_at, active_jobs) "
                    "VALUES (:worker_id, now(), :active_jobs)"
                ),
                {"worker_id": self.id, "active_jobs": self._active_jobs},
            )
            session.execute(
                text("UPDATE workers SET last_seen_at = now() WHERE id = :id"), {"id": self.id}
            )
            session.commit()

    # -- claiming --------------------------------------------------------------

    def claim_batch(self, batch_size: int) -> list[dict]:
        with self.Session() as session:
            result = session.execute(
                CLAIM_SQL, {"worker_id": self.id, "queue_id": self.queue_id, "batch_size": batch_size}
            )
            rows = result.mappings().all()
            session.commit()
            return [dict(r) for r in rows]

    # -- execution -------------------------------------------------------------

    def execute_job(self, job: dict):
        job_id = job["id"]
        attempt_number = job["attempt_count"] + 1
        self._active_jobs += 1

        execution_id = uuid.uuid4()
        started = datetime.now(timezone.utc)

        with self.Session() as session:
            session.execute(
                text(
                    "UPDATE jobs SET status = 'running', updated_at = now() WHERE id = :id"
                ),
                {"id": job_id},
            )
            session.execute(
                text(
                    "INSERT INTO job_executions (id, job_id, worker_id, attempt_number, status, started_at) "
                    "VALUES (:eid, :job_id, :worker_id, :attempt_number, 'running', :started_at)"
                ),
                {
                    "eid": execution_id,
                    "job_id": job_id,
                    "worker_id": self.id,
                    "attempt_number": attempt_number,
                    "started_at": started,
                },
            )
            session.commit()

        self.logger.info(f"Started job {job_id} (type={job['type']}, attempt={attempt_number})")

        error_message = None
        try:
            run_handler(job["type"], job["payload"])
            final_status = "completed"
        except Exception as exc:  # noqa: BLE001 - deliberately broad, this is a generic executor
            final_status = "failed"
            error_message = str(exc)
            self.logger.warning(f"Job {job_id} failed: {error_message}")

        finished = datetime.now(timezone.utc)
        duration_ms = int((finished - started).total_seconds() * 1000)

        with self.Session() as session:
            session.execute(
                text(
                    "UPDATE jobs SET status = :status, attempt_count = :attempt_count, updated_at = now() "
                    "WHERE id = :id"
                ),
                {"status": final_status, "attempt_count": attempt_number, "id": job_id},
            )
            session.execute(
                text(
                    "UPDATE job_executions SET status = :status, finished_at = :finished_at, "
                    "duration_ms = :duration_ms, error_message = :error_message WHERE id = :eid"
                ),
                {
                    "status": final_status,
                    "finished_at": finished,
                    "duration_ms": duration_ms,
                    "error_message": error_message,
                    "eid": execution_id,
                },
            )
            session.commit()

        self.logger.info(f"Finished job {job_id} -> {final_status} ({duration_ms}ms)")
        self._active_jobs -= 1

    # -- main loop ---------------------------------------------------------------

    def request_shutdown(self, *_):
        self.logger.info("Shutdown requested — will stop claiming new jobs and wait for in-flight jobs to finish")
        self._shutdown = True

    def run(self):
        signal.signal(signal.SIGINT, self.request_shutdown)
        signal.signal(signal.SIGTERM, self.request_shutdown)

        self.register()
        last_heartbeat = 0.0

        try:
            while not self._shutdown:
                now = time.monotonic()
                if now - last_heartbeat >= self.heartbeat_interval:
                    self.send_heartbeat()
                    last_heartbeat = now

                self._in_flight = [f for f in self._in_flight if not f.done()]
                available_slots = self.concurrency - len(self._in_flight)

                if available_slots > 0:
                    jobs = self.claim_batch(available_slots)
                    for job in jobs:
                        future = self._executor.submit(self.execute_job, job)
                        self._in_flight.append(future)

                time.sleep(self.poll_interval)

            self.logger.info(f"Waiting for {len(self._in_flight)} in-flight job(s) to finish...")
            for f in self._in_flight:
                f.result()

        finally:
            self._executor.shutdown(wait=True)
            self.deregister(final_status="offline")


def main():
    parser = argparse.ArgumentParser(description="Distributed Job Scheduler worker process")
    parser.add_argument("--database-url", default=None, help="Overrides DATABASE_URL env/settings")
    parser.add_argument("--project-id", required=True, type=uuid.UUID)
    parser.add_argument("--queue-id", required=True, type=uuid.UUID)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--heartbeat-interval", type=float, default=5.0)
    args = parser.parse_args()

    if args.database_url:
        database_url = args.database_url
    else:
        sys.path.insert(0, ".")
        from app.core.config import settings
        database_url = settings.DATABASE_URL

    worker = Worker(
        database_url=database_url,
        project_id=args.project_id,
        queue_id=args.queue_id,
        concurrency=args.concurrency,
        poll_interval=args.poll_interval,
        heartbeat_interval=args.heartbeat_interval,
    )
    worker.run()


if __name__ == "__main__":
    main()
