# Technical Architecture Document
## Distributed Job Scheduler

---

## 1. System Overview

The Distributed Job Scheduler is a multi-component system where users create queues and submit jobs to them, and a fleet of independent worker processes claims and executes those jobs — concurrently, reliably, without ever executing the same job twice.

The system is organized into four independently deployable components:

```
                     ┌──────────────────────┐
                     │   React Dashboard     │
                     │   (Vite + Tailwind)   │
                     └──────────┬────────────┘
                                │ HTTPS / WSS
                                ▼
                     ┌──────────────────────┐
                     │    FastAPI Server     │
                     │  - Auth (JWT)         │
                     │  - REST API           │
                     │  - WebSocket          │
                     │  - Rate limiting      │
                     └──────────┬────────────┘
                                │ SQL
                                ▼
                     ┌──────────────────────┐
                     │     PostgreSQL        │◄──── Source of truth
                     │   (single broker)     │      for all state
                     └──────────▲────────────┘
                                │ SQL (claim/poll)
               ┌────────────────┼────────────────┐
               ▼                ▼                ▼
        ┌──────────┐    ┌──────────┐    ┌──────────┐
        │ Worker 1 │    │ Worker 2 │    │ Worker N │
        │ poll     │    │ poll     │    │ poll     │
        │ claim    │    │ claim    │    │ claim    │
        │ execute  │    │ execute  │    │ execute  │
        │ heartbeat│    │ heartbeat│    │ heartbeat│
        └──────────┘    └──────────┘    └──────────┘

        ┌──────────────────────┐
        │   Reaper Process     │  (single background process)
        │  - stale job sweep   │
        │  - zombie recovery   │
        └──────────────────────┘
```

**Why four components, not a monolith:**
- The API server is stateless — it can scale behind a load balancer without any coordination.
- Workers scale on a different dimension than the API (CPU/IO bound by job execution, not HTTP traffic).
- The reaper is logically separate because "detect stuck jobs" is a different responsibility from "execute jobs" — conflating them would mean every worker runs cron-like sweeps redundantly.
- All coordination flows through PostgreSQL, not a message broker, which gives us transactional correctness for free (explained further in §5).

---

## 2. Job Lifecycle

```
Submit job
     │
     ▼
 [QUEUED] ─── run_at in future ──► [SCHEDULED]
     │                                  │
     │◄──────────── run_at reached ─────┘
     │
     │  SELECT ... FOR UPDATE SKIP LOCKED
     ▼
 [CLAIMED]  (worker holds row lock)
     │
     ▼
 [RUNNING]  (heartbeat updated periodically)
     │
     ├──► [COMPLETED]  (success)
     │
     └──► handler raised ──► retry policy check
               │
        ┌──────┴──────┐
        ▼             ▼
   attempts        attempts
   < max_retries   = max_retries
        │             │
   [SCHEDULED]   [DEAD_LETTER]
   (back-off)    (DLQ entry created)

  Crash path (reaper):
  Worker heartbeat goes stale ──► reaper detects ──► same retry/DLQ decision
```

Recurring (cron) jobs use a separate `scheduled_jobs` table as a template. The Scheduler process (not yet extracted — currently the worker can trigger it, or it can be a separate cron tick) generates a fresh `jobs` row on each fire rather than reusing one row. This is the standard pattern (Sidekiq, Celery, Airflow all do the same) because it gives you clean per-run execution history.

---

## 3. Atomic Job Claiming — The Core Concurrency Mechanism

The most important engineering decision in the system: how do multiple workers claim jobs without ever claiming the same one twice?

```sql
UPDATE jobs
SET status = 'claimed', worker_id = :worker_id, claimed_at = now(), updated_at = now()
WHERE id IN (
    SELECT j.id FROM jobs j
    WHERE j.queue_id = :queue_id
      AND j.status IN ('queued', 'scheduled')
      AND j.run_at <= now()
      AND (
          j.depends_on_job_id IS NULL
          OR EXISTS (
              SELECT 1 FROM jobs dep
              WHERE dep.id = j.depends_on_job_id AND dep.status = 'completed'
          )
      )
    ORDER BY j.priority DESC, j.run_at ASC
    FOR UPDATE OF j SKIP LOCKED
    LIMIT :batch_size
)
RETURNING id, type, payload, attempt_count, retry_policy_id;
```

The key clause: `FOR UPDATE SKIP LOCKED`.

When a row is being updated (claimed) by worker A, it holds an exclusive row lock. `SKIP LOCKED` tells worker B's query to skip that row entirely rather than blocking on it — so B immediately moves to the next available job. This achieves:

- **No double-claiming** — the same row cannot be inside two `UPDATE...WHERE id IN (SELECT...FOR UPDATE)` transactions simultaneously.
- **No blocking** — workers never queue up waiting for each other's row locks.
- **Single round-trip** — claim and status-update happen atomically in one SQL statement.

**Proof:** In testing, 3 concurrent worker processes processed 60 jobs simultaneously. The result: exactly 60 job execution rows, zero jobs executed twice, load distributed naturally (15/22/23 across workers).

The dependency gate (`depends_on_job_id IS NULL OR EXISTS(...)`) is part of the same query, so a job waiting on a dependency is never claimable — with no extra round trips and no polling overhead.

---

## 4. Data Model (12 Entities)

```
Users ──1──< Organizations ──1──< Projects ──1──< Queues ──1──< Jobs
                                                      │            │
                                                      │            ├──< JobExecutions
                                              RetryPolicies        ├──< JobLogs
                                                                   └──< DeadLetterQueue

                                                  Queues ──1──< ScheduledJobs
                                                  Projects ──1──< Workers
                                                  Workers ──1──< WorkerHeartbeats
```

**Key indexing decisions:**

The hottest table in the system is `jobs`. Every worker's claim loop hits this table every poll interval. The partial index that makes this viable at scale:

```sql
CREATE INDEX idx_jobs_claim_candidate
ON jobs (queue_id, status, run_at, priority DESC)
WHERE status IN ('queued', 'scheduled');
```

This is a **partial index** — it only indexes rows a worker can actually claim. As millions of completed jobs accumulate in the table, the index stays small and the claim query stays fast. Without it, the claim query degrades to a sequential scan as the table grows.

**One deliberate denormalization:** `jobs.attempt_count` duplicates what could be derived with `COUNT(*) FROM job_executions WHERE job_id = ...`. It's kept on the `jobs` row because it appears in the hot-path claim query (`WHERE attempt_count < max_retries`). A join/aggregate on every claim cycle would kill throughput. The denormalization is kept consistent by updating both `jobs.attempt_count` and inserting a `job_executions` row in the same transaction.

---

## 5. Technology Stack and Rationale

| Component | Technology | Why |
|---|---|---|
| API server | FastAPI (Python) | Async I/O, automatic OpenAPI docs, Pydantic validation |
| Database | PostgreSQL 16 | Row-level locking, `SKIP LOCKED`, strong consistency |
| ORM / migrations | SQLAlchemy 2.0 + Alembic | Type-safe models, versioned schema |
| Worker | Python (same codebase as API) | Shares models/config, simpler deployment |
| Frontend | React 18 + Vite + Tailwind CSS | Fast iteration, matches team's existing stack |
| Containerization | Docker Compose | One-command local dev + easy demo |
| Rate limiting | slowapi | FastAPI-native, supports per-user keying via JWT |
| Auth | JWT (python-jose + passlib/bcrypt) | Stateless, no session store needed |

---

## 6. Reliability Mechanisms

### Retry strategies
Each queue has a default `RetryPolicy` (strategy: fixed/linear/exponential, base_delay, max_retries, max_delay). Individual jobs can override. On failure, delay is computed with up to 10% jitter to prevent thundering-herd retry storms.

```python
# Exponential: delay = min(base * 2^(attempt-1), max_delay) + jitter
delay = min(base_delay * (2 ** (attempt_number - 1)), max_delay)
delay += random.uniform(0, delay * 0.1)
```

### Graceful shutdown
Workers catch `SIGTERM` (the standard Kubernetes/Docker termination signal), set a `_shutdown` flag, stop claiming new jobs, and wait for all in-flight jobs to complete before exiting. A worker receiving `SIGTERM` 2 seconds into a 15-second job will wait 13 more seconds, finish the job cleanly, mark itself offline, and exit — rather than abandoning the job mid-flight.

### Crash recovery (reaper)
`SIGKILL`, OOM-kill, and host crashes can't be caught by the worker. The reaper detects these by monitoring `workers.last_seen_at`: if a worker's heartbeat goes stale beyond a threshold (default: 30 seconds), its in-flight jobs are requeued or dead-lettered, and it's marked offline. Critically, a crash counts as a consumed attempt — a job whose worker keeps getting killed will eventually exhaust its `max_retries` and land in the DLQ, rather than retrying forever.

---

## 7. Bonus Features

### Workflow dependencies
`jobs.depends_on_job_id` — a self-referential FK. The claim SQL's `WHERE` clause gates on the dependency's status being `completed`. The gating is in SQL, not application logic, so no worker can race around it.

### WebSocket live updates
`GET /api/v1/ws/queues/{queue_id}/jobs?token=...` — authenticated WebSocket that pushes a fresh job snapshot every 1.5 seconds. Authentication reuses the same JWT decode as REST endpoints. The dashboard's job table switches between WebSocket-driven (no filters active) and REST-polling (when filters are active) transparently.

### Rate limiting
Login: 10 requests/minute. Register: 5 requests/minute. Job creation: 100 requests/minute. Batch creation: 20 requests/minute. Keyed by JWT subject when authenticated (IP rotation can't bypass it), IP for unauthenticated endpoints. Uses slowapi's in-memory store (suitable for single-instance; switch to Redis store for multi-replica deployments).

---

## 8. What Is Intentionally Not In This Build

| Skipped | Reason |
|---|---|
| Redis message broker | Postgres `SKIP LOCKED` gives equivalent atomicity with fewer moving parts. Redis would add throughput at the cost of transactional correctness guarantees. Worth revisiting if the system needs >10,000 jobs/second. |
| gRPC worker dispatch | Polling is simpler, self-healing (a dead dispatcher strands nothing), and naturally load-balances. Trade-off is up to one poll-interval latency per job. |
| Kafka / Kinesis | No requirement for event replay or fan-out to multiple consumer groups. Adds operational complexity with no benefit at this scale. |
| Multi-region Postgres | Out of scope for this build. Would require Citus or read-replica routing. |
