"""Alert rules, evaluation engine and escalation policies."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from src.monitoring.metrics import MetricsCollector


class Comparison(str, Enum):
    """Supported threshold comparisons."""

    GREATER_THAN = "gt"
    LESS_THAN = "lt"
    GREATER_EQUAL = "gte"
    LESS_EQUAL = "lte"
    EQUAL = "eq"
    NOT_EQUAL = "neq"


_OPERATIONS = {
    Comparison.GREATER_THAN: lambda v, t: v > t,
    Comparison.LESS_THAN: lambda v, t: v < t,
    Comparison.GREATER_EQUAL: lambda v, t: v >= t,
    Comparison.LESS_EQUAL: lambda v, t: v <= t,
    Comparison.EQUAL: lambda v, t: v == t,
    Comparison.NOT_EQUAL: lambda v, t: v != t,
}


@dataclass(slots=True)
class AlertRule:
    """Threshold rule evaluated against the latest value of one metric."""

    name: str
    metric: str
    threshold: float
    comparison: Comparison = Comparison.GREATER_THAN
    severity: str = "warning"
    channels: list[str] = field(default_factory=lambda: ["slack"])
    labels: dict[str, str] | None = None

    def matches(self, value: float) -> bool:
        operation = _OPERATIONS[self.comparison]
        return bool(operation(value, self.threshold))


class AlertState(str, Enum):
    FIRING = "firing"
    RESOLVED = "resolved"


@dataclass(slots=True)
class Alert:
    """An alert instance tracked from firing through resolution."""

    rule: AlertRule
    value: float
    state: AlertState
    fired_at: datetime
    resolved_at: datetime | None = None

    @property
    def age_minutes(self) -> float:
        end = self.resolved_at or datetime.now(timezone.utc)
        delta = end - self.fired_at
        return delta.total_seconds() / 60.0


class EscalationPolicy:
    """Time-based channel escalation for unresolved alerts."""

    def __init__(self, steps: list[tuple[float, str]]) -> None:
        if not steps:
            raise ValueError("escalation policy needs at least one step")
        self.steps = sorted(steps, key=lambda s: s[0])

    def channel_for(self, age_minutes: float) -> str:
        """Return the channel responsible once an alert is ``age_minutes`` old."""
        channel = self.steps[0][1]
        for after_minutes, step_channel in self.steps:
            if age_minutes >= after_minutes:
                channel = step_channel
        return channel


class AlertManager:
    """Evaluates rules against a collector and deduplicates firing alerts."""

    def __init__(
        self,
        rules: list[AlertRule] | None = None,
        escalation: EscalationPolicy | None = None,
    ) -> None:
        self.rules = list(rules or [])
        self.escalation = escalation
        self.active: dict[str, Alert] = {}
        self.history: list[Alert] = []

    def add_rule(self, rule: AlertRule) -> None:
        self.rules.append(rule)

    def evaluate(self, collector: MetricsCollector) -> list[Alert]:
        """Run every rule; returns alerts currently in the FIRING state."""

        firing_now: list[str] = []
        for rule in self.rules:
            series = collector.query(rule.metric, rule.labels)
            latest = series.latest() if series else None
            if latest is not None and rule.matches(latest):
                existing = self.active.get(rule.name)
                if existing is None:
                    alert = Alert(
                        rule=rule,
                        value=latest,
                        state=AlertState.FIRING,
                        fired_at=datetime.now(timezone.utc),
                    )
                    self.active[rule.name] = alert
                    self.history.append(alert)
                firing_now.append(rule.name)

        for name, alert in list(self.active.items()):
            if name not in firing_now:
                alert.state = AlertState.RESOLVED
                alert.resolved_at = datetime.now(timezone.utc)
                del self.active[name]

        return [self.active[name] for name in firing_now]

    def notify_channels(self, alert: Alert) -> list[str]:
        """Resolve which channels should page for this alert right now."""
        base = list(alert.rule.channels)
        if self.escalation is not None:
            escalated = self.escalation.channel_for(alert.age_minutes)
            if escalated not in base:
                base.append(escalated)
        return base
