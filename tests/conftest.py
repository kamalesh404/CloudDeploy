"""Shared pytest fixtures for the CloudDeploy test suite."""

from __future__ import annotations

import pytest

from src.deploy.strategy import Release
from src.infra.state import LocalStateBackend
from src.monitoring.metrics import MetricsCollector
from src.providers.base import (
    CloudProvider,
    ProvisionedResource,
    ResourceKind,
    ResourceSpec,
    ResourceStatus,
)
from src.templates import get_template


class FakeProvider(CloudProvider):
    """Deterministic in-memory provider used to test provider-agnostic code."""

    name = "fake"
    display_name = "Fake Cloud"

    def __init__(self) -> None:
        super().__init__(region="fake-region-1")
        self._counter = 0

    @property
    def supported_kinds(self) -> frozenset[ResourceKind]:
        return frozenset(ResourceKind)

    def provision(self, spec: ResourceSpec) -> ProvisionedResource:
        self._counter += 1
        resource = ProvisionedResource(
            spec=spec,
            provider_id=f"fake-{self._counter:04d}-{spec.name}",
            status=ResourceStatus.ACTIVE,
            endpoints=[f"{spec.name}.fake.cloud"],
        )
        self._resources[resource.provider_id] = resource
        return resource

    def destroy(self, provider_id: str) -> bool:
        resource = self._resources.get(provider_id)
        if resource is None:
            return False
        resource.status = ResourceStatus.DESTROYED
        return True

    def get_status(self, provider_id: str) -> ResourceStatus:
        resource = self._resources.get(provider_id)
        return ResourceStatus.FAILED if resource is None else resource.status


@pytest.fixture()
def fake_provider() -> FakeProvider:
    """Fresh fake provider instance per test."""
    return FakeProvider()


@pytest.fixture()
def state_backend(tmp_path) -> LocalStateBackend:
    """Local state backend rooted inside the pytest temp directory."""
    return LocalStateBackend(tmp_path / "state.json")


@pytest.fixture()
def web_app_specs() -> list[ResourceSpec]:
    """Rendered specs from the web-app template."""
    template = get_template("web-app")
    return template.render({"app_name": "shop"})


@pytest.fixture()
def stack_document() -> dict:
    """Minimal valid clouddeploy.yaml document as a parsed mapping."""
    return {
        "name": "shop",
        "provider": "fake",
        "region": "us-east-1",
        "template": "web-app",
        "variables": {"app_name": "shop"},
    }


@pytest.fixture()
def collector() -> MetricsCollector:
    """Collector pre-seeded with a small deterministic cpu series."""
    metrics = MetricsCollector()
    for value in (10.0, 20.0, 30.0, 40.0):
        metrics.record("cpu_percent", value, {"service": "api"})
    return metrics


@pytest.fixture()
def release() -> Release:
    """Standard three-replica release used by strategy tests."""
    return Release(version="v2.0.0", image="registry.example.com/shop:v2.0.0", replicas=3)
