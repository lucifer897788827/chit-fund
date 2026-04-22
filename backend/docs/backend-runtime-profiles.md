# Backend Runtime Profiles

The backend uses one FastAPI API process plus separate Celery worker and beat processes in production.

## Environment Modes

- `APP_ENV=production` enables production defaults for connection pools, logging, and readiness behavior.
- `APP_ENV=development` or `APP_ENV=local` keeps the app fail-open for readiness probes so local work stays unblocked when Redis or the broker are offline.
- `DATABASE_URL` and `JWT_SECRET` are required.
- `REDIS_URL` defaults to `redis://localhost:6379/0`.
- `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND` default to `REDIS_URL` unless explicitly overridden.

## Operational Endpoints

- `GET /api/health` returns the legacy lightweight health response.
- `GET /api/health/readiness` reports detailed readiness for `database`, `redis`, and `celeryBroker`.
- In production, readiness returns HTTP `503` when any dependency is down.
- In local development, readiness still returns HTTP `200` but the payload shows which checks failed.

## Production Start Commands

Run these from `backend/` after exporting the current envs.

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

```bash
celery -A app.core.celery_app:celery_app worker --loglevel=INFO
```

For Supabase session-pooler environments with limited DB connections, prefer the safer low-concurrency worker profile:

```bash
celery -A app.core.celery_app:celery_app worker -P solo -c 1 --loglevel=INFO
```

```bash
celery -A app.core.celery_app:celery_app beat --loglevel=INFO
```

## Recommended Production Env

- `APP_ENV=production`
- `DATABASE_URL=postgresql+psycopg://...`
- `JWT_SECRET=...`
- `REDIS_URL=redis://...`
- Optional overrides:
  - `CELERY_BROKER_URL`
  - `CELERY_RESULT_BACKEND`
  - `DATABASE_POOL_SIZE`
  - `DATABASE_MAX_OVERFLOW`
  - `DATABASE_POOL_TIMEOUT_SECONDS`
  - `DATABASE_POOL_RECYCLE_SECONDS`
  - `REDIS_MAX_CONNECTIONS`
  - `REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS`
  - `REDIS_SOCKET_TIMEOUT_SECONDS`
  - `REDIS_HEALTH_CHECK_INTERVAL_SECONDS`
  - `CELERY_BROKER_POOL_LIMIT`

Keep the API, worker, and beat pointed at the same database and Redis deployment so readiness reflects the real production topology.
