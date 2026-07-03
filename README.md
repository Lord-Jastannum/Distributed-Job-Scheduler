# Distributed Job Scheduler — Phase 1

Auth + Organizations/Projects/Queues CRUD backend.

## Setup

```bash
docker compose up --build
```

API available at http://localhost:8000, interactive docs at http://localhost:8000/docs

## Run migrations (only if not auto-applied)

```bash
docker compose exec api alembic upgrade head
```

## Run tests

```bash
docker compose exec api pytest tests/ -v
```
