"""Core abstractions shared by every cloud provider implementation."""

from __future__ import annotations

import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, ClassVar

NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{2,30}$")


class ResourceKind(str, Enum):
    """Categories of cloud resources CloudDeploy can manage."""

    COMPUTE = "compute"
    STORAGE = "storage"
    DATABASE = "database"
    NETWORK = "network"
    CDN = "cdn"
    QUEUE = "queue"


class ResourceStatus(str, Enum):
    """Lifecycle states for a provisioned cloud resource."""

    PENDING = "pending"
    CREATING = "creating"
    ACTIVE = "active"
    UPDATING = "updating"
    FAILED = "failed"
    DESTROYING = "destroying"
    DESTROYED = "destroyed"


@dataclass(slots=True)
class ResourceSpec:
    """Declarative description of a single desired cloud resource."""

    kind: ResourceKind
    name: str
    region: str = "us-east-1"
    size: str = "small"
    replicas: int = 1
    tags: dict[str, str] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)

    def merged_tags(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        """Return this spec's tags overlaid with provider-injected defaults."""
        base = {"managed-by": "clouddeploy", "resource": self.name}
        base.update(self.tags)
        if extra:
            base.update(extra)
        return base


@dataclass(slots=True)
class ProvisionedResource:
    """A concrete resource created by a provider from a :class:`ResourceSpec`."""

    spec: ResourceSpec
    provider_id: str
    status: ResourceStatus = ResourceStatus.CREATING
    endpoints: list[str] = field(default_factory=list)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


class ProviderError(Exception):
    """Raised when a provider fails to fulfil an operation."""


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def new_resource_id(prefix: str) -> str:
    """Generate a provider-style opaque identifier with the given prefix."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class CloudProvider(ABC):
    """Contract every cloud backend must implement to join the registry."""

    name: ClassVar[str] = "abstract"
    display_name: ClassVar[str] = "Abstract Cloud"

    def __init__(self, region: str = "us-east-1", **kwargs: Any) -> None:
        self.region = region
        self.options = kwargs
        self._resources: dict[str, ProvisionedResource] = {}

    @property
    def supported_kinds(self) -> frozenset[ResourceKind]:
        """The resource kinds this provider knows how to provision."""
        raise NotImplementedError

    @abstractmethod
    def provision(self, spec: ResourceSpec) -> ProvisionedResource:
        """Create the described resource and return its record."""

    @abstractmethod
    def destroy(self, provider_id: str) -> bool:
        """Tear down a previously provisioned resource."""

    @abstractmethod
    def get_status(self, provider_id: str) -> ResourceStatus:
        """Report the current lifecycle status of a resource; FAILED if unknown."""

    def list_resources(self) -> list[ProvisionedResource]:
        """List every resource this client instance has provisioned."""
        return list(self._resources.values())

    def validate_spec(self, spec: ResourceSpec) -> list[str]:
        """Return human-readable errors for an invalid spec; empty means OK."""
        errors: list[str] = []
        if not NAME_PATTERN.match(spec.name):
            errors.append(
                f"name {spec.name!r} must match {NAME_PATTERN.pattern} (3-31 chars)",
            )
        if spec.replicas < 1 or spec.replicas > 64:
            errors.append(f"replicas must be between 1 and 64, got {spec.replicas}")
        if spec.kind not in self.supported_kinds:
            errors.append(f"{self.name} does not support kind {spec.kind.value!r}")
        return errors
