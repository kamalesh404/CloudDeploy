"""Observability commands: ``logs``, ``metrics`` and ``alerts``."""

from __future__ import annotations

import json
import pathlib

import click

from src.monitoring.alerts import AlertManager, AlertRule, Comparison
from src.monitoring.logs import LogAggregator, LogEntry, SearchQuery, parse_level
from src.monitoring.metrics import Dashboard, MetricsCollector, Panel


def _make_entry(level: str, service: str, message: str) -> LogEntry:
    return LogEntry(level=parse_level(level), service=service, message=message)


def _load_log_file(path: pathlib.Path) -> LogAggregator:
    """Ingest JSONL records of the shape {"level","service","message"}."""
    aggregator = LogAggregator()
    if not path.exists():
        raise click.ClickException(f"log file {path} not found")
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise click.ClickException(f"{path}:{line_number}: invalid JSON ({exc})") from exc
        aggregator.ingest(
            _make_entry(
                str(record.get("level", "info")),
                str(record.get("service", "unknown")),
                str(record.get("message", "")),
            ),
        )
    return aggregator


@click.command()
@click.option("--file", "log_path", type=pathlib.Path, default=pathlib.Path("deploy.log"))
@click.option("--service", default=None, help="Restrict output to one service.")
@click.option("--level", default="info", show_default=True, help="Minimum severity.")
@click.option("--grep", default=None, help="Regex applied to message bodies.")
@click.option("--limit", default=50, show_default=True, help="Maximum lines shown.")
def logs(log_path: pathlib.Path, service: str | None, level: str, grep: str | None, limit: int) -> None:
    """Search aggregated logs from a deployed stack."""
    aggregator = _load_log_file(log_path)
    query = SearchQuery(
        text=grep,
        service=service,
        min_level=parse_level(level),
        limit=limit,
    )
    matches = aggregator.search(query)
    if not matches:
        click.echo("No log entries matched the given filters.")
        return
    for entry in matches:
        click.echo(entry.render())


@click.command(name="metrics")
@click.option("--metric", default=None, help="Show percentiles for a single metric name.")
@click.option("--values", default=None, help="Comma-separated values to analyse.")
def metrics(metric: str | None, values: str | None) -> None:
    """Show dashboard summaries or per-metric percentile breakdowns."""
    collector = MetricsCollector()
    if metric and values:
        for raw in values.split(","):
            collector.record(metric, float(raw))
        series_values = collector.all_values(metric)
        click.echo(f"metric={metric} count={len(series_values)}")
        for pct in (50, 90, 95, 99):
            value = collector.percentile(metric, float(pct))
            formatted = f"{value:.2f}" if value is not None else "-"
            click.echo(f"  p{pct}: {formatted}")
        return

    dashboard = Dashboard(
        name="production-overview",
        panels=[
            Panel(title="HTTP latency", metric="http_latency_ms", unit="ms"),
            Panel(title="CPU utilisation", metric="cpu_percent", unit="%"),
            Panel(title="Queue depth", metric="queue_depth", unit="jobs"),
        ],
    )
    click.echo(f"Dashboard: {dashboard.name}")
    for row in dashboard.render(collector):
        avg = row["avg"]
        p95 = row["p95"]
        avg_text = f"{avg:.1f}" if isinstance(avg, float) else "-"
        p95_text = f"{p95:.1f}" if isinstance(p95, float) else "-"
        click.echo(f"  {row['title']:<18} count={row['count']:<5} avg={avg_text:<10} p95={p95_text}")


@click.command()
@click.option("--cpu", type=float, default=None, help="Current cpu_percent reading to evaluate.")
@click.option("--threshold", type=float, default=80.0, show_default=True, help="Alert threshold.")
def alerts(cpu: float | None, threshold: float) -> None:
    """Evaluate alert rules against the latest metrics snapshot."""
    collector = MetricsCollector()
    manager = AlertManager(
        rules=[
            AlertRule(
                name="high-cpu",
                metric="cpu_percent",
                threshold=threshold,
                comparison=Comparison.GREATER_THAN,
                severity="critical",
                channels=["pagerduty"],
            ),
        ],
    )
    if cpu is not None:
        collector.record("cpu_percent", cpu)

    firing = manager.evaluate(collector)
    if not firing:
        click.secho("All clear: no alert rules are firing.", fg="green")
        return
    for alert in firing:
        channels = ", ".join(manager.notify_channels(alert))
        click.secho(
            f"FIRING {alert.rule.name}: cpu={alert.value:.1f} "
            f"threshold={alert.rule.comparison.value}{alert.rule.threshold:g} "
            f"severity={alert.rule.severity} -> {channels}",
            fg="red",
        )
