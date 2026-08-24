"""State backends persisting the mapping of stacks to provisioned resources."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from src.providers.base import ProvisionedResource, ResourceKind, ResourceStatus


def resource_to_entry(resource: ProvisionedResource) -> dict[str, Any]:
    """Serialise a provisioned resource into a JSON-safe state record."""

    return {
        "name": resource.spec.name,
        "kind": resource.spec.kind.value,
        "region": resource.spec.region,
        "size": resource.spec.size,
        "replicas": resource.spec.replicas,
        "tags": dict(resource.spec.tags),
        "config": dict(resource.spec.config),
        "provider_id": resource.provider_id,
        "status": resource.status.value,
        "endpoints": list(resource.endpoints),
    }


class StateBackend(ABC):
    """Storage contract for stack state, mirroring Terraform backends."""

    @abstractmethod
    def load(self, stack: str) -> list[dict[str, Any]]:
        """Return recorded entries for a stack; empty list when absent."""

    @abstractmethod
    def save(self, stack: str, resources: list[ProvisionedResource]) -> None:
        """Replace the stored record set for a stack."""

    @abstractmethod
    def delete(self, stack: str) -> bool:
        """Forget a stack entirely; returns False if it was never stored."""

    @abstractmethod
    def list_stacks(self) -> list[str]:
        """Names of every stack tracked by this backend."""


class LocalStateBackend(StateBackend):
    """Filesystem backend storing all state in one JSON document."""

    def __init__(self, path: str | Path = ".clouddeploy/state.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({})

    def _read(self) -> dict[str, list[dict[str, Any]]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict[str, list[dict[str, Any]]]) -> None:
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def load(self, stack: str) -> list[dict[str, Any]]:
        return [dict(entry) for entry in self._read().get(stack, [])]

    def save(self, stack: str, resources: list[ProvisionedResource]) -> None:
        data = self._read()
        data[stack] = [resource_to_entry(resource) for resource in resources]
        self._write(data)

    def delete(self, stack: str) -> bool:
        data = self._read()
        if stack not in data:
            return False
        del data[stack]
        self._write(data)
        return True

    def list_stacks(self) -> list[str]:
        return sorted(self._read())


class S3StateBackend(StateBackend):
    """S3-style backend with an injectable client or in-memory fallback.

    ``client`` is duck-typed against the three boto3 calls used here so
    tests can pass fakes; when omitted, an internal dictionary simulates
    the bucket which keeps local runs dependency-free.
    """

    def __init__(self, bucket: str, client: Any | None = None) -> None:
        self.bucket = bucket
        self.client = client
        self.objects: dict[str, bytes] = {}

    def _key(self, stack: str) -> str:
        return f"stacks/{stack}.json"

    def load(self, stack: str) -> list[dict[str, Any]]:
        key = self._key(stack)
        raw = (
            self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
            if self.client
            else self.objects.get(key)
        )
        if not raw:
            return []
        return json.loads(raw)

    def save(self, stack: str, resources: list[ProvisionedResource]) -> None:
        payload = json.dumps(
            [resource_to_entry(resource) for resource in resources],
            indent=2,
        ).encode("utf-8")
        if self.client:
            self.client.put_object(Bucket=self.bucket, Key=self._key(stack), Body=payload)
        else:
            self.objects[self._key(stack)] = payload

    def delete(self, stack: str) -> bool:
        key = self._key(stack)
        exists = bool(
            self.objects.pop(key, None)
            if self.client is None
            else getattr(self.client, "head_object", lambda **kw: True)(Bucket=self.bucket, Key=key),
        )
        if self.client and exists:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        return exists


def entry_to_summary(entry: dict[str, Any]) -> str:
    """Compact one-line rendering used by ``clouddeploy status``."""
    status = entry.get("status", ResourceStatus.PENDING.value)
    kind = entry.get("kind", ResourceKind.COMPUTE.value)
    return f"{entry['name']:<24} {kind:<10} {status:<10} {entry.get('provider_id', '-')}"
