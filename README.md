# Distributed Job Scheduler

A production-grade distributed job scheduling system built with FastAPI, PostgreSQL, React, and Docker Compose. Supports immediate, delayed, scheduled, recurring (cron), and batch job execution across multiple concurrent worker processes — with atomic job claiming, retry strategies, a dead letter queue, and a real-time monitoring dashboard.

---

## Quick Start

**Prerequisites:** Docker Desktop running, ports 8000 and 5173 free.

```bash
git clone <your-repo-url>
cd job-scheduler
docker compose up --build
```

In a second terminal:
```bash
docker compose exec api alembic upgrade head
```

| Service | URL |
|---|---|
| Dashboard | http://localhost:5173 |
| API (Swagger docs) | http://localhost:8000/docs |
| API (health check) | http://localhost:8000/health |

---

## Running the Worker

The worker is a separate process that polls the queue and executes jobs. Run it inside the `api` container (shares the same Postgres connection string):

```bash
docker compose exec api python worker/worker.py \
  --project-id <your-project-id> \
  --queue-id <your-queue-id> \
  --concurrency 5
```

Get your `project-id` and `queue-id` from the dashboard sidebar or from the Swagger UI after creating an org → project → queue.

To run multiple workers in parallel (real distributed execution):
```bash
# Terminal 2
docker compose exec api python worker/worker.py --project-id <id> --queue-id <id> --concurrency 5

# Terminal 3
docker compose exec api python worker/worker.py --project-id <id> --queue-id <id> --concurrency 5
```

---

## Running the Reaper

The reaper detects jobs stuck because their worker crashed (SIGKILL, OOM, host failure) and requeues or dead-letters them. Run it alongside the API and workers:

```bash
docker compose exec api python worker/reaper.py \
  --stale-after-seconds 30 \
  --interval 10
```

---

## Running Tests

```bash
docker compose exec api pytest tests/ -v
```

Expected output: `28 passed`.

---

## Project Structure

```
job-scheduler/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # REST endpoints + WebSocket
│   │   ├── core/            # Config, DB session, security, rate limiter, retry math
│   │   ├── models/          # SQLAlchemy ORM models (12 entities)
│   │   └── schemas/         # Pydantic request/response schemas
│   ├── worker/
│   │   ├── worker.py        # Worker process (claim, execute, heartbeat, graceful shutdown)
│   │   └── reaper.py        # Reaper process (zombie job recovery)
│   ├── alembic/             # Database migrations (5 versioned migrations)
│   └── tests/               # Automated test suite (28 tests across 5 files)
└── frontend/
    └── src/
        ├── pages/           # Login, Dashboard
        └── components/      # Sidebar, JobTable, JobCreateForm, WorkersPanel, DlqPanel
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://scheduler:scheduler@postgres:5432/scheduler` | Postgres connection string |
| `SECRET_KEY` | `dev-secret-change-me` | JWT signing secret — **change for production** |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | JWT TTL (24 hours) |

---

## API Authentication

All endpoints except `POST /api/v1/auth/register` and `POST /api/v1/auth/login` require a Bearer token.

```bash
# Register
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"yourpassword","name":"Your Name"}'

# Login → copy the access_token
curl -X POST http://localhost:8000/api/v1/auth/login \
  -d "username=you@example.com&password=yourpassword"

# Use the token
curl http://localhost:8000/api/v1/organizations \
  -H "Authorization: Bearer <your_token>"
```
