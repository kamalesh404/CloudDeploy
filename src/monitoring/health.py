"""Health checks and uptime monitoring for deployed endpoints."""

from __future__ import annotations

import time
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Deque

Probe = Callable[[str], tuple[int, float]]
"""A probe receives an endpoint URL and returns (status_code, latency_ms)."""


@dataclass(slots=True)
class HealthCheck:
    """Declarative description of a single endpoint probe."""

    name: str
    endpoint: str
    interval_seconds: float = 30.0
    timeout_seconds: float = 5.0
    expected_status: int = 200


@dataclass(slots=True)
class HealthResult:
    """Outcome of one executed health check."""

    check_name: str
    healthy: bool
    status_code: int | None
    latency_ms: float | None
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    detail: str = ""


def default_probe(endpoint: str) -> tuple[int, float]:
    """Perform a real HTTP GET used when no injected probe is supplied."""
    start = time.perf_counter()
    with urllib.request.urlopen(endpoint, timeout=5) as response:
        code = getattr(response, "status", 200)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return int(code), round(elapsed_ms, 2)


def perform_check(check: HealthCheck, probe: Probe | None = None) -> HealthResult:
    """Execute ``check`` once using the given or default probe."""
    probe = probe or default_probe
    try:
        status_code, latency = probe(check.endpoint)
    except Exception as exc:  # noqa: BLE001 - probes may raise anything
        return HealthResult(
            check_name=check.name,
            healthy=False,
            status_code=None,
            latency_ms=None,
            detail=str(exc),
        )
    return HealthResult(
        check_name=check.name,
        healthy=status_code == check.expected_status,
        status_code=status_code,
        latency_ms=latency,
        detail="ok" if status_code == check.expected_status else f"unexpected status {status_code}",
    )


class HealthMonitor:
    """Tracks rolling history per registered check and derives uptime stats."""

    def __init__(self, history_size: int = 100, unhealthy_threshold: int = 3) -> None:
        self.history_size = history_size
        self.unhealthy_threshold = unhealthy_threshold
        self.checks: dict[str, HealthCheck] = {}
        self.results: dict[str, Deque[HealthResult]] = {}

    def register(self, check: HealthCheck) -> None:
        self.checks[check.name] = check
        self.results.setdefault(check.name, deque(maxlen=self.history_size))

    def record(self, result: HealthResult) -> None:
        if result.check_name not in self.checks:
            raise KeyError(f"check {result.check_name!r} is not registered")
        self.results[result.check_name].append(result)

    def run(self, name: str, probe: Probe | None = None) -> HealthResult:
        """Run a registered check by name and store the outcome."""
        result = perform_check(self.checks[name], probe)
        self.record(result)
        return result

    def uptime_percent(self, name: str) -> float | None:
        results = list(self.results.get(name, ()))
        if not results:
            return None
        healthy = sum(1 for r in results if r.healthy)
        return round(100.0 * healthy / len(results), 2)

    def consecutive_failures(self, name: str) -> int:
        count = 0
        for result in reversed(list(self.results.get(name, ()))):
            if result.healthy:
                break
            count += 1
        return count

    def overall_status(self, min_uptime: float = 99.0) -> str:
        """Aggregate verdict across checks: healthy, degraded or down."""

        if not self.checks:
            return "unknown"
        statuses = []
        for name in self.checks:
            uptime = self.uptime_percent(name)
            if uptime is None:
                statuses.append("unknown")
            elif self.consecutive_failures(name) >= self.unhealthy_threshold:
                statuses.append("down")
            elif uptime >= min_uptime:
                statuses.append("healthy")
            else:
                statuses.append("degraded")
        if any(s == "down" for s in statuses):
            return "down"
        if all(s == "healthy" for s in statuses):
            return "healthy"
        return "degraded"
