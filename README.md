# Staff & Skill Planning Tool

Backend service for employee and skill management with a multi-step onboarding workflow.
Python 3.13 · FastAPI · SQLAlchemy (async) · PostgreSQL · Alembic · uv · pytest · Docker.

## Problem understanding

Team leads track people and skills in scattered spreadsheets, so questions like
"who knows Kubernetes at an advanced level?" need ad-hoc polling. The service must:

1. **Import employees** from a CSV file and persist them.
2. **List employees** with their skills, and **search** by skill and minimum proficiency.
3. **Assign / update skills** and proficiency levels for an employee.
4. **Onboard** every imported employee across at least three downstream systems
   (HR, IT, access/security). A failure in one step must be handled cleanly, so the
   system never ends up in a silently half-applied state, without paid or heavy orchestrators.

## Assumptions

- The downstream systems (HR, IT services, access/security) are **simulated** in
  `src/external/`. They can be slow or fail, and they accept an **idempotency key**,
  so repeating a call is safe.
- An employee is identified by **email**, which is stored lower-cased and is unique.
- CSV columns are `first_name, last_name, email, start_date` (ISO date). Header spacing
  is tolerated. Invalid rows are reported and skipped, they don't fail the whole file.
  Rows whose email already exists, in the DB or earlier in the file, are skipped, so
  re-uploading the same file is safe.
- Onboarding is triggered by **import**. A separate "activation" step does not exist,
  because imported employees are onboarded straight away.
- Skill names are free text, matched **case-insensitively** ("Python" = "python"). The
  first-seen casing is displayed. Proficiency is one of `beginner`, `intermediate`,
  `advanced`, `expert`.
- "Minimum proficiency" means at that level or higher, evaluated against a **single**
  skill when combined with the skill filter.
- One PostgreSQL instance is the system of record. No authentication, since the tool is
  internal and sits behind the company's network and gateway.
- Eventual consistency is acceptable for the downstream systems. The employee record
  is saved immediately and provisioning completes shortly after.

## Approach

- **Import and onboarding are decoupled with a transactional outbox.** In one DB
  transaction the import saves the employees *and* one provisioning task per service
  per employee. The slow external calls happen afterwards, outside the request, so
  an HTTP request never blocks on, or half-completes because of, a downstream system.
- **Tasks are durable and retried.** Each task is a Celery job (RabbitMQ broker) that
  calls the service and records the outcome. Transient errors are retried with
  exponential backoff and jitter. Permanent failures, or exhausted attempts, end as
  `failed` rows that are kept as a dead letter, and operators can see them via the API.
- **No partial state without a trace.** The employee and its tasks commit together or
  not at all. Each service's state is tracked per employee, so a half-onboarded
  employee is visible and recoverable instead of silently inconsistent.
- **Failure isolation.** A per-service circuit breaker stops hammering a failing
  service. Its tasks are rescheduled after the cooldown and don't burn retry attempts.
- **Safe under concurrency.** The database's unique indexes arbitrate races
  (`INSERT ... ON CONFLICT DO NOTHING`), and finished tasks are skipped on redelivery,
  so duplicate or parallel requests and multiple workers don't clash.

## Design

```
POST /employees/import
   │  parse + validate CSV, skip bad / duplicate rows
   ▼
 ┌──────────────── one DB transaction ────────────────┐
 │ INSERT employees (ON CONFLICT (email) DO NOTHING)  │
 │ INSERT provisioning_task × 3 per new employee      │
 └────────────────────────────────────────────────────┘
   │ commit → enqueue provision(task_id) × 3   (response returns here)
   ▼
 Celery worker (RabbitMQ)
   load task, skip if finished  →  call service (idempotency key)
     ├─ ok                → succeeded
     ├─ transient error   → self.retry, exponential backoff
     ├─ circuit open      → self.retry after cooldown, no attempt charged
     └─ permanent / max attempts → failed (dead letter, last_error kept)
```

| Concern | Choice |
|---|---|
| Layers | `api` (HTTP) → `services` (use cases) → `db` managers (queries) → models |
| Services called | `hr_operations`, `it_services`, `access_provision` (simulated) |
| Delivery | At-least-once, made safe by idempotency keys `employee-{id}:{service}` |
| Crash safety | Late acks: if a worker dies mid-task, RabbitMQ redelivers the message |
| Attempt budget | Kept in the task row (`attempts`), so it survives redelivery and worker restarts |
| Migrations | Alembic, applied automatically when the container starts |

**API** (prefix `/api/v1`, Swagger at `/docs`)

| Method | Path | Purpose |
|---|---|---|
| POST | `/employees/import` | Upload a CSV (`file`). Returns `created`, `skipped`, `errors`, `provisioning_queued` |
| GET | `/employees?skill=&min_proficiency=&page=` | Paged list (20 per page) with skills, filterable |
| PUT | `/employees/{id}/skills` | Replace an employee's skills and proficiencies |
| GET | `/employees/{id}/provisioning` | Per-service onboarding status, attempts and last error |

**Known limitations / trade-offs**

- There is no automatic *undo* of services that already succeeded when a sibling
  service permanently fails. The failure is recorded as a dead letter and shown in the
  provisioning status for follow-up. Compensating calls would need undo operations on
  the downstream systems, which the simulated services don't have.
- If RabbitMQ is down at import time the employees and tasks are still saved, but the
  jobs are not enqueued and stay `pending` until re-dispatched. Several workers are
  safe, but circuit-breaker state is per worker process.
- Import pre-checks each email with its own query, and inserts in one statement, which
  is fine for typical HR-sized files but not for very large ones (tens of thousands of rows).

## Code link

Repository: https://github.com/deepakhared-info/employee-onboarding

```
src/
  app.py, routes.py        FastAPI app, routing
  celery_app.py            Celery app (RabbitMQ broker)
  onboarding/              employees & skills: api, services, db, models, schemas
  provisioning/            task status model, Celery task (calls, retry), status API
  external/                simulated HR / IT / access services + circuit-breaker wrapper
  core/                    settings, errors, CSV reader, retry/backoff + circuit breaker
  db/                      engine/session, base model, generic CRUD manager
migrations/                Alembic revisions
tests/                     api, services, provisioning
```

## Tests

```bash
uv sync
uv run pytest
```

Covers the HTTP layer (validation, status codes, error mapping), the import service
(valid, invalid and duplicate rows, rows won by a concurrent import, rollback and no dispatch
on DB failure), skill assignment rules, and the provisioning processor (success,
retries with backoff, permanent failure, exhausted attempts, open circuit, lost claim).
Database access is mocked in unit tests.

## Deployment Details

- **Container:** multi-stage `Dockerfile` built with `uv` from the lockfile.
  - `dev` target: source is bind-mounted and uvicorn runs with `--reload` (used by Compose).
  - `runtime` target (default): minimal image, non-root user, no dev dependencies. It
    is the one to ship to AWS ECS.
- **Startup:** the container runs `alembic upgrade head` and then starts uvicorn, so
  the schema is always current before traffic arrives. If a migration fails the
  container exits.
- **Configuration** (environment variables, or a `.env` file):

  | Variable | Default | Meaning |
  |---|---|---|
  | `SQLALCHEMY_DATABASE_URI` | – | PostgreSQL connection string (required) |
  | `CELERY_BROKER_URL` | `amqp://guest:guest@localhost:5672//` | RabbitMQ connection string |
  | `PROVISIONING_MAX_ATTEMPTS` | `5` | Attempts before a task is marked failed |
  | `PROVISIONING_BACKOFF_BASE` / `_CAP` | `2` / `300` | Retry backoff in seconds |
  | `EXTERNAL_CALL_TIMEOUT` | `10` | Per-call timeout (seconds) |
  | `CIRCUIT_FAILURE_THRESHOLD` / `_RECOVERY_TIMEOUT` | `5` / `30` | Circuit breaker tuning |

- **CI/CD:** no pipeline is checked in yet. A GitHub Actions workflow would run
  `uv sync --frozen`, `uv run pytest`, build the `runtime` image, and push it to ECR on
  `main`, ready for an ECS deploy.
- **ECS notes:** run migrations once per release (a one-off task) when running more than
  one replica, and point `SQLALCHEMY_DATABASE_URI` at RDS PostgreSQL.

## How to run

**With Docker (recommended)**

```bash
docker compose up --build -d
```

This starts PostgreSQL, RabbitMQ, the Celery worker and the API, and applies the migrations automatically.
Open the [Swagger docs](http://localhost:8080/docs).

Try it:

```bash
# import the sample file
curl -F "file=@employee.csv" http://localhost:8080/api/v1/employees/import

# assign skills
curl -X PUT http://localhost:8080/api/v1/employees/1/skills \
  -H 'content-type: application/json' \
  -d '{"skills":[{"name":"Kubernetes","proficiency":"advanced"}]}'

# search
curl "http://localhost:8080/api/v1/employees?skill=kubernetes&min_proficiency=intermediate"

# onboarding status
curl http://localhost:8080/api/v1/employees/1/provisioning
```

**Locally (without Docker)**

```bash
uv sync
export SQLALCHEMY_DATABASE_URI=postgresql://postgres:postgres@localhost:5432/app
uv run alembic upgrade head
uv run uvicorn main:app --reload --port 8080

# in another terminal (needs RabbitMQ on localhost:5672)
uv run celery -A src.celery_app worker --loglevel=info
```
