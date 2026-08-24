"""In-memory time-series metrics collection and dashboard rendering."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

Labels = dict[str, str]


@dataclass(slots=True)
class MetricPoint:
    """A single timestamped measurement."""

    value: float
    timestamp: float = field(default_factory=time.time)


@dataclass(slots=True)
class MetricSeries:
    """Ordered points for one metric identified by name and label set."""

    name: str
    labels: Labels = field(default_factory=dict)
    points: list[MetricPoint] = field(default_factory=list)

    def append(self, value: float, timestamp: float | None = None) -> None:
        point = MetricPoint(value=value) if timestamp is None else MetricPoint(value=value, timestamp=timestamp)
        self.points.append(point)

    @property
    def values(self) -> list[float]:
        return [p.value for p in self.points]

    def latest(self) -> float | None:
        return self.points[-1].value if self.points else None

    def average(self, window_seconds: float | None = None) -> float | None:
        values = self.values
        if window_seconds is not None:
            cutoff = time.time() - window_seconds
            values = [p.value for p in self.points if p.timestamp >= cutoff]
        if not values:
            return None
        return sum(values) / len(values)


def percentile(values: list[float], pct: float) -> float | None:
    """Linear-interpolated percentile over sorted input values."""

    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100.0) * (len(ordered) - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    fraction = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


class MetricsCollector:
    """Registry of metric series keyed by ``(name, frozenset(labels))``."""

    def __init__(self) -> None:
        self._series: dict[tuple[str, tuple[tuple[str, str], ...]], MetricSeries] = {}

    @staticmethod
    def _key(name: str, labels: Labels | None) -> tuple[str, tuple[tuple[str, str], ...]]:
        normalised = tuple(sorted((labels or {}).items()))
        return name, normalised

    def record(self, name: str, value: float, labels: Labels | None = None) -> None:
        key = self._key(name, labels)
        series = self._series.get(key)
        if series is None:
            series = MetricSeries(name=name, labels=dict(labels or {}))
            self._series[key] = series
        series.append(value)

    def query(self, name: str, labels: Labels | None = None) -> MetricSeries | None:
        return self._series.get(self._key(name, labels))

    def all_values(self, name: str) -> list[float]:
        return [
            point.value
            for key, series in self._series.items()
            if key[0] == name
            for point in series.points
        ]

    def names(self) -> list[str]:
        return sorted({key[0] for key in self._series})

    def percentile(self, name: str, pct: float) -> float | None:
        return percentile(self.all_values(name), pct)


@dataclass(slots=True)
class Panel:
    """One chart on a dashboard bound to a metric name."""

    title: str
    metric: str
    unit: str = "ms"

    def render(self, collector: MetricsCollector) -> dict[str, object]:
        values = collector.all_values(self.metric)
        return {
            "title": self.title,
            "metric": self.metric,
            "unit": self.unit,
            "count": len(values),
            "avg": sum(values) / len(values) if values else None,
            "p95": percentile(values, 95.0),
        }


@dataclass(slots=True)
class Dashboard:
    """Named collection of panels for CLI rendering."""

    name: str
    panels: list[Panel] = field(default_factory=list)

    def render(self, collector: MetricsCollector) -> list[dict[str, object]]:
        return [panel.render(collector) for panel in self.panels]
