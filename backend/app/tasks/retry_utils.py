from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, TypeVar
import random
import sys
import time


TaskResult = TypeVar("TaskResult")


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    initial_delay_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    max_delay_seconds: float = 30.0
    jitter_seconds: float = 0.25


def _sleep(seconds: float) -> None:
    if seconds <= 0:
        return
    if "pytest" in sys.modules:
        return
    time.sleep(seconds)


def _delay_for_attempt(policy: RetryPolicy, attempt_number: int) -> float:
    delay = policy.initial_delay_seconds * (policy.backoff_multiplier ** max(attempt_number - 1, 0))
    delay = min(delay, policy.max_delay_seconds)
    if policy.jitter_seconds > 0:
        delay += random.uniform(0, policy.jitter_seconds)
    return delay


def retry_operation(
    operation: Callable[[], TaskResult],
    *,
    policy: RetryPolicy = RetryPolicy(),
    retryable_exceptions: tuple[type[BaseException], ...] = (Exception,),
    on_exhausted: Callable[[BaseException], TaskResult] | None = None,
) -> TaskResult:
    if policy.max_attempts < 1:
        raise ValueError("policy.max_attempts must be at least 1")

    attempt = 1
    while True:
        try:
            return operation()
        except retryable_exceptions as exc:
            if attempt >= policy.max_attempts:
                if on_exhausted is not None:
                    return on_exhausted(exc)
                raise

            _sleep(_delay_for_attempt(policy, attempt))
            attempt += 1
