from __future__ import annotations

import argparse
import os
from time import perf_counter
from typing import Iterable

import httpx

DEFAULT_ENDPOINTS = [
    ("login", "POST", "/api/auth/login"),
    ("dashboard", "GET", "/api/users/me/dashboard"),
    ("admin users", "GET", "/api/admin/users"),
    ("finalize jobs", "GET", "/api/admin/finalize-jobs"),
]


def summarize_timings(timings: dict[str, list[float]]) -> list[dict[str, float | str]]:
    report = []
    for endpoint, values in timings.items():
        average_ms = sum(values) / len(values) if values else 0.0
        report.append({"endpoint": endpoint, "averageMs": round(average_ms, 2)})
    return report


def format_report(rows: Iterable[dict[str, float | str]]) -> str:
    lines = ["Endpoint -> Avg Time"]
    for row in rows:
        lines.append(f"{row['endpoint']} -> {float(row['averageMs']):.2f}ms")
    return "\n".join(lines)


def measure_endpoints(
    *,
    base_url: str,
    endpoints: Iterable[tuple[str, str, str]] = DEFAULT_ENDPOINTS,
    iterations: int = 3,
    bearer_token: str | None = None,
) -> list[dict[str, float | str]]:
    headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}
    timings: dict[str, list[float]] = {name: [] for name, _method, _path in endpoints}

    with httpx.Client(base_url=base_url.rstrip("/"), timeout=10.0) as client:
        for _ in range(iterations):
            for name, method, path in endpoints:
                started_at = perf_counter()
                if method.upper() == "POST":
                    response = client.request(method, path)
                else:
                    response = client.request(method, path, headers=headers)
                duration_ms = (perf_counter() - started_at) * 1000
                timings[name].append(duration_ms)
                response.close()

    return summarize_timings(timings)


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure core API endpoint timings.")
    parser.add_argument("--base-url", default=os.getenv("PERF_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--iterations", type=int, default=int(os.getenv("PERF_ITERATIONS", "3")))
    args = parser.parse_args()

    rows = measure_endpoints(
        base_url=args.base_url,
        iterations=max(args.iterations, 1),
        bearer_token=os.getenv("PERF_BEARER_TOKEN"),
    )
    print(format_report(rows))


if __name__ == "__main__":
    main()
