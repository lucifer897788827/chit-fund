from app.tasks.retry_utils import RetryPolicy, retry_operation


def test_retry_operation_retries_transient_errors_and_returns_success(monkeypatch):
    attempts = []
    sleeps = []

    monkeypatch.setattr("app.tasks.retry_utils._sleep", lambda seconds: sleeps.append(seconds))

    def operation():
        attempts.append("attempt")
        if len(attempts) < 2:
            raise ConnectionError("temporary outage")
        return {"status": "ok"}

    result = retry_operation(
        operation,
        policy=RetryPolicy(max_attempts=3, initial_delay_seconds=1.0, backoff_multiplier=2.0, jitter_seconds=0),
        retryable_exceptions=(ConnectionError,),
    )

    assert result == {"status": "ok"}
    assert len(attempts) == 2
    assert sleeps == [1.0]


def test_retry_operation_invokes_exhausted_callback_after_final_failure(monkeypatch):
    attempts = []
    sleeps = []

    monkeypatch.setattr("app.tasks.retry_utils._sleep", lambda seconds: sleeps.append(seconds))

    def operation():
        attempts.append("attempt")
        raise TimeoutError("still down")

    result = retry_operation(
        operation,
        policy=RetryPolicy(max_attempts=3, initial_delay_seconds=0.5, backoff_multiplier=2.0, jitter_seconds=0),
        retryable_exceptions=(TimeoutError,),
        on_exhausted=lambda exc: {
            "status": "failed",
            "error": str(exc),
        },
    )

    assert result == {"status": "failed", "error": "still down"}
    assert len(attempts) == 3
    assert sleeps == [0.5, 1.0]
