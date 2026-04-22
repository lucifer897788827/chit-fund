# Structured Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add lightweight structured application and request logging for FastAPI startup and request lifecycle, with JSON defaulting on in production and opt-in elsewhere.

**Architecture:** Keep logging concerns isolated in a small core module that owns formatter and logger setup, then wire a single FastAPI middleware plus a lifespan startup log in `app.main`. Use existing settings for environment-driven defaults and keep request payloads small and non-sensitive.

**Tech Stack:** FastAPI, standard `logging`, `pytest`, `TestClient`

---

### Task 1: Describe the logging contract with tests

**Files:**
- Create: `backend/tests/test_logging.py`

- [ ] **Step 1: Write the failing test**

```python
def test_resolve_structured_logging_defaults_by_environment():
    assert resolve_structured_logging("production", None) is True
    assert resolve_structured_logging("development", None) is False
    assert resolve_structured_logging("development", True) is True
    assert resolve_structured_logging("production", False) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_logging.py -v`
Expected: FAIL because `app.core.logging` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
def resolve_structured_logging(app_env: str, configured_value: bool | None) -> bool:
    normalized_env = app_env.lower().strip()
    if configured_value is not None:
        return configured_value
    return normalized_env in {"production", "prod"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_logging.py -v`
Expected: PASS after the helper is added.

### Task 2: Add JSON formatting and request lifecycle logging

**Files:**
- Create: `backend/app/core/logging.py`
- Create: `backend/tests/test_logging.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/core/config.py`

- [ ] **Step 1: Write the failing test**

```python
def test_json_formatter_serializes_request_metadata():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="app",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="http.request.completed",
        args=(),
        exc_info=None,
    )
    record.request_id = "req-123"
    record.method = "GET"
    record.path = "/api/health"
    record.status_code = 200
    payload = json.loads(formatter.format(record))
    assert payload["event"] == "http.request.completed"
    assert payload["request_id"] == "req-123"
    assert payload["path"] == "/api/health"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_logging.py::test_json_formatter_serializes_request_metadata -v`
Expected: FAIL because `JsonFormatter` is not implemented yet.

- [ ] **Step 3: Write minimal implementation**

```python
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in STANDARD_RECORD_FIELDS and not key.startswith("_"):
                payload[key] = value
        return json.dumps(payload, separators=(",", ":"), default=str)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_logging.py -v`
Expected: PASS after formatter and middleware wiring are added.

### Task 3: Wire startup/request logs into FastAPI

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/core/config.py`
- Create: `backend/app/core/logging.py`

- [ ] **Step 1: Write the failing test**

```python
def test_fastapi_emits_startup_and_request_logs_as_json(capsys):
    configure_logging(app_env="development", structured_logging=True)
    with TestClient(app) as client:
        response = client.get("/api/health", headers={"x-request-id": "req-abc"})
    assert response.status_code == 200
    lines = [json.loads(line) for line in capsys.readouterr().err.splitlines() if line.strip()]
    events = [line["event"] for line in lines if "event" in line]
    assert "app.startup" in events
    completed = next(line for line in lines if line.get("event") == "http.request.completed")
    assert completed["request_id"] == "req-abc"
    assert completed["status_code"] == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_logging.py::test_fastapi_emits_startup_and_request_logs_as_json -v`
Expected: FAIL because the app does not yet emit structured logs.

- [ ] **Step 3: Write minimal implementation**

```python
@asynccontextmanager
async def lifespan(_app: FastAPI):
    bootstrap_database()
    app_logger.info("app.startup", extra={"event": "app.startup", "app_env": settings.app_env})
    yield


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid4().hex
    started = perf_counter()
    app_logger.info(
        "http.request.started",
        extra={"event": "http.request.started", "request_id": request_id, "method": request.method, "path": request.url.path},
    )
    try:
        response = await call_next(request)
    except Exception:
        app_logger.exception(
            "http.request.failed",
            extra={"event": "http.request.failed", "request_id": request_id, "method": request.method, "path": request.url.path},
        )
        raise
    duration_ms = (perf_counter() - started) * 1000
    app_logger.info(
        "http.request.completed",
        extra={"event": "http.request.completed", "request_id": request_id, "method": request.method, "path": request.url.path, "status_code": response.status_code, "duration_ms": round(duration_ms, 2)},
    )
    return response
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_logging.py -v`
Expected: PASS with JSON output for startup and request completion.

