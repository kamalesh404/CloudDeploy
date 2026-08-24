"""Centralised log ingestion, search, tailing and streaming."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum


class LogLevel(IntEnum):
    """Severity ordering; higher values are more severe."""

    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50

    @property
    def label(self) -> str:
        return self.name


@dataclass(slots=True)
class LogEntry:
    """One structured log line emitted by a deployed service."""

    level: LogLevel
    service: str
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    attributes: dict[str, str] = field(default_factory=dict)

    def render(self) -> str:
        stamp = self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        attrs = " ".join(f"{k}={v}" for k, v in sorted(self.attributes.items()))
        suffix = f" {attrs}" if attrs else ""
        return f"{stamp} {self.level.label:<8} {self.service:<16} {self.message}{suffix}"


_LEVEL_ALIASES = {
    "debug": LogLevel.DEBUG,
    "info": LogLevel.INFO,
    "warn": LogLevel.WARNING,
    "warning": LogLevel.WARNING,
    "error": LogLevel.ERROR,
    "critical": LogLevel.CRITICAL,
}


def parse_level(value: str) -> LogLevel:
    """Coerce a human string such as ``warning`` into a :class:`LogLevel`."""
    try:
        return _LEVEL_ALIASES[value.strip().lower()]
    except KeyError as exc:
        valid = ", ".join(sorted(_LEVEL_ALIASES))
        raise ValueError(f"unknown log level {value!r}; expected one of {valid}") from exc


@dataclass(slots=True)
class SearchQuery:
    """Composable filters for :meth:`LogAggregator.search`."""

    text: str | None = None
    service: str | None = None
    min_level: LogLevel = LogLevel.DEBUG
    since: datetime | None = None
    limit: int = 100

    def matches(self, entry: LogEntry) -> bool:
        if entry.level < self.min_level:
            return False
        if self.service and entry.service != self.service:
            return False
        if self.since and entry.timestamp < self.since:
            return False
        if self.text and not re.search(self.text, entry.message, re.IGNORECASE):
            return False
        return True


class LogAggregator:
    """In-memory sink that ingests entries and answers filtered queries.

    Entries are kept in insertion order. ``stream`` yields newly appended
    records to followers, polling with a configurable interval so the CLI
    can implement ``logs --follow`` without external infrastructure.
    """

    def __init__(self, max_entries: int = 10_000) -> None:
        self.entries: list[LogEntry] = []
        self.max_entries = max_entries

    def ingest(self, *entries: LogEntry) -> int:
        self.entries.extend(entries)
        overflow = len(self.entries) - self.max_entries
        if overflow > 0:
            del self.entries[:overflow]
        return len(entries)

    def search(self, query: SearchQuery | None = None) -> list[LogEntry]:
        query = query or SearchQuery()
        matched = [entry for entry in reversed(self.entries) if query.matches(entry)]
        return list(reversed(matched[-query.limit:]))

    def tail(self, count: int = 20) -> list[LogEntry]:
        return self.entries[-count:]

    def stream(
        self,
        cursor: int = 0,
        poll_interval: float = 0.1,
        max_iterations: int = 100,
    ):
        """Yield entries appended after ``cursor`` until the caller stops."""

        position = max(cursor, 0)
        iterations = 0
        while iterations < max_iterations:
            iterations += 1
            fresh = self.entries[position:]
            for entry in fresh:
                yield entry
                position += 1
            if len(self.entries) > self.max_entries:
                position = max(0, position - (len(self.entries) - self.max_entries))
            if not fresh and poll_interval > 0:
                time.sleep(poll_interval)


def make_entry(level: str, service: str, message: str, **attrs: str) -> LogEntry:
    """Convenience constructor used by CLI commands and tests."""
    return LogEntry(level=parse_level(level), service=service, message=message, attributes=dict(attrs))
