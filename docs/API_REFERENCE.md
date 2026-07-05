# API Reference
## Distributed Job Scheduler — v0.1.0

Base URL: `http://localhost:8000/api/v1`

Interactive docs (Swagger UI): `http://localhost:8000/docs`

All endpoints except `/auth/register` and `/auth/login` require:
```
Authorization: Bearer <access_token>
```

All error responses follow this shape:
```json
{
  "error": {
    "code": 422,
    "message": "Validation failed",
    "details": [...]
  }
}
```

---

## Auth

### POST /auth/register
Create a new user account.

**Rate limit:** 5 requests/minute per IP.

**Request body:**
```json
{
  "email": "user@example.com",
  "password": "minlength8",
  "name": "Your Name"
}
```

**Response `201`:**
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "name": "Your Name",
  "created_at": "2026-01-01T00:00:00Z"
}
```

**Errors:** `409` email already registered, `422` validation failed.

---

### POST /auth/login
Authenticate and receive a JWT token.

**Rate limit:** 10 requests/minute per IP.

**Request body** (form-encoded, not JSON):
```
username=user@example.com&password=yourpassword
```

**Response `200`:**
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer"
}
```

**Errors:** `401` incorrect credentials, `429` rate limit exceeded.

---

## Organizations

### POST /organizations
Create a new organization. The authenticated user becomes the owner.

**Request body:**
```json
{ "name": "Acme Corp" }
```

**Response `201`:** Organization object.

---

### GET /organizations
List organizations owned by the authenticated user.

**Query params:** `page` (default 1), `page_size` (default 20, max 100).

---

### GET /organizations/{org_id}
Get a single organization. Returns `403` if not the owner.

---

## Projects

### POST /organizations/{org_id}/projects
Create a project inside an organization.

**Request body:**
```json
{ "name": "Backend Services" }
```

**Response `201`:** Project object.

---

### GET /organizations/{org_id}/projects
List projects in an organization.

**Query params:** `page`, `page_size`.

---

## Queues

### POST /projects/{project_id}/queues
Create a queue with an optional default retry policy.

**Request body:**
```json
{
  "name": "email-notifications",
  "priority": 5,
  "concurrency_limit": 10,
  "retry_policy": {
    "strategy": "exponential",
    "base_delay_seconds": 5,
    "max_retries": 5,
    "max_delay_seconds": 3600
  }
}
```

`strategy` must be `"fixed"`, `"linear"`, or `"exponential"`.

**Response `201`:** Queue object.

**Errors:** `409` queue name already exists in this project.

---

### GET /projects/{project_id}/queues
List queues in a project.

**Query params:** `status` (filter by `active` or `paused`), `page`, `page_size`.

---

### GET /queues/{queue_id}
Get a single queue.

---

### PATCH /queues/{queue_id}
Update a queue's priority, concurrency_limit, or status.

**Request body** (all fields optional):
```json
{
  "priority": 10,
  "concurrency_limit": 20,
  "status": "paused"
}
```

---

### POST /queues/{queue_id}/pause
Pause a queue. Paused queues stop accepting new jobs and workers skip them during claiming.

---

### POST /queues/{queue_id}/resume
Resume a paused queue.

---

## Jobs

### POST /queues/{queue_id}/jobs
Submit a single job.

**Rate limit:** 100 requests/minute per authenticated user.

**Request body:**
```json
{
  "type": "send_email",
  "payload": { "to": "user@example.com", "subject": "Hello" },
  "run_at": "2026-06-01T09:00:00Z",
  "priority": 5,
  "idempotency_key": "order-123-confirmation",
  "depends_on_job_id": "uuid-of-prerequisite-job"
}
```

All fields except `type` are optional.

- `run_at` omitted or `<= now()` → `status: "queued"` (immediate execution)
- `run_at > now()` → `status: "scheduled"` (delayed execution)
- `idempotency_key` — if a job with this key already exists in the queue, returns `409` instead of creating a duplicate.
- `depends_on_job_id` — this job won't be claimed until the referenced job's `status` is `"completed"`. Must reference a job in the same queue.

**Response `201`:** Job object.

**Errors:** `409` idempotency key collision or paused queue, `422` invalid `depends_on_job_id`.

---

### POST /queues/{queue_id}/jobs/batch
Submit multiple jobs in one request, all tagged with a shared `batch_id`.

**Rate limit:** 20 requests/minute per authenticated user.

**Request body:**
```json
{
  "jobs": [
    { "type": "resize_image", "payload": { "image_id": 1 } },
    { "type": "resize_image", "payload": { "image_id": 2 } }
  ]
}
```

Max 500 jobs per request. `batch_id` is auto-generated and returned on all job objects.

**Response `201`:** Array of Job objects.

---

### GET /queues/{queue_id}/jobs
List jobs in a queue with optional filters.

**Query params:**
- `status` — filter by status (`queued`, `scheduled`, `claimed`, `running`, `completed`, `failed`, `dead_letter`)
- `type` — filter by job type string
- `batch_id` — filter to a specific batch
- `page`, `page_size`

---

### GET /jobs/{job_id}
Get a single job by ID.

---

### GET /jobs/{job_id}/executions
Get the execution history for a job — one row per attempt.

**Response:**
```json
[
  {
    "id": "uuid",
    "job_id": "uuid",
    "worker_id": "uuid",
    "attempt_number": 1,
    "status": "failed",
    "started_at": "...",
    "finished_at": "...",
    "duration_ms": 312,
    "error_message": "Connection timeout"
  }
]
```

---

## Scheduled (Recurring) Jobs

### POST /queues/{queue_id}/scheduled-jobs
Create a recurring (cron) or one-off scheduled job template.

**Request body — recurring:**
```json
{
  "type": "daily_report",
  "payload_template": { "format": "pdf" },
  "cron_expression": "0 9 * * 1-5"
}
```

**Request body — one-off delayed:**
```json
{
  "type": "send_reminder",
  "payload_template": {},
  "run_once_at": "2026-12-25T09:00:00Z"
}
```

Exactly one of `cron_expression` or `run_once_at` must be provided. Invalid cron expressions return `422`. `run_once_at` must be in the future.

**Response `201`:** ScheduledJob object including computed `next_run_at`.

---

### GET /queues/{queue_id}/scheduled-jobs
List scheduled job templates for a queue.

---

### POST /scheduled-jobs/{scheduled_job_id}/deactivate
Deactivate a recurring job template. Existing spawned jobs are not affected.

---

## Workers

### GET /projects/{project_id}/workers
List all workers that have registered for a project.

**Response:**
```json
[
  {
    "id": "uuid",
    "project_id": "uuid",
    "hostname": "worker-host-1",
    "status": "online",
    "registered_at": "...",
    "last_seen_at": "..."
  }
]
```

`status` is one of `online`, `offline`, `draining`.

---

### GET /workers/{worker_id}/heartbeats
Get recent heartbeats for a worker (most recent first).

**Query params:** `limit` (default 20, max 200).

---

## Dead Letter Queue

### GET /queues/{queue_id}/dead-letter-queue
List jobs in the dead letter queue for this queue.

**Query params:** `include_resolved` (default `false` — hide resolved entries).

**Response:**
```json
[
  {
    "id": "uuid",
    "job_id": "uuid",
    "final_error": "Simulated failure for job type 'send_email'",
    "attempt_count": 3,
    "moved_at": "...",
    "resolved": false
  }
]
```

---

### POST /dead-letter-queue/{dlq_id}/replay
Reset the job's `attempt_count` to 0, set status back to `queued`, and mark the DLQ entry as resolved. The job will be picked up by the next available worker.

**Response `200`:** Updated Job object.

---

### POST /dead-letter-queue/{dlq_id}/dismiss
Mark the DLQ entry as resolved without re-queuing the job. Use when the job had bad input data that isn't worth retrying.

**Response `200`:** Updated DLQ entry object.

---

## WebSocket

### WS /api/v1/ws/queues/{queue_id}/jobs

Authenticated WebSocket that streams live job status updates for a queue.

**Authentication:** Pass the JWT token as a query parameter:
```
ws://localhost:8000/api/v1/ws/queues/{queue_id}/jobs?token=<access_token>
```

Invalid or expired tokens result in immediate close with HTTP 403.

**Messages received** (server → client):
```json
{
  "type": "jobs_snapshot",
  "jobs": [
    {
      "id": "uuid",
      "type": "send_email",
      "status": "running",
      "priority": 0,
      "attempt_count": 1,
      "run_at": "...",
      "updated_at": "..."
    }
  ]
}
```

Snapshots are pushed every 1.5 seconds. The payload contains the 50 most recently updated jobs for the queue. This is used by the dashboard's job table to show live status updates without manual refresh.

---

## Job Status Reference

| Status | Description |
|---|---|
| `queued` | Eligible for claiming immediately |
| `scheduled` | Waiting until `run_at` — or waiting for a dependency to complete |
| `claimed` | A worker has row-locked this job and is about to start execution |
| `running` | Worker is actively executing the job handler |
| `completed` | Handler returned successfully |
| `failed` | Handler raised an exception; job will be retried or dead-lettered |
| `dead_letter` | Exhausted all retry attempts; manual intervention required |
