"""Google Cloud Platform provider covering GCE, Cloud Run, Cloud SQL and GCS."""

from __future__ import annotations

from typing import Any

from src.providers.base import (
    CloudProvider,
    ProvisionedResource,
    ProviderError,
    ResourceKind,
    ResourceSpec,
    ResourceStatus,
    new_resource_id,
)

MACHINE_SIZES: dict[str, str] = {
    "micro": "e2-micro",
    "small": "e2-small",
    "medium": "e2-medium",
    "large": "n2-standard-4",
    "xlarge": "n2-standard-16",
}

SUPPORTED_REGIONS = frozenset(
    {"us-central1", "us-east1", "europe-west1", "asia-southeast1"},
)


class GCPProvider(CloudProvider):
    """Manage Google Cloud resources through a uniform spec interface."""

    name = "gcp"
    display_name = "Google Cloud Platform"

    def __init__(self, region: str = "us-central1", project: str = "default", **kwargs: Any) -> None:
        super().__init__(region=region, **kwargs)
        if region not in SUPPORTED_REGIONS:
            raise ProviderError(f"unsupported GCP region {region!r}")
        self.project = project
        self.zone = f"{region}-a"

    @property
    def supported_kinds(self) -> frozenset[ResourceKind]:
        return frozenset(
            {
                ResourceKind.COMPUTE,
                ResourceKind.STORAGE,
                ResourceKind.DATABASE,
                ResourceKind.NETWORK,
                ResourceKind.CDN,
                ResourceKind.QUEUE,
            },
        )

    def provision(self, spec: ResourceSpec) -> ProvisionedResource:
        """Provision a resource, prefixing ids with the owning project."""
        handlers = {
            ResourceKind.COMPUTE: self._provision_compute,
            ResourceKind.STORAGE: self._provision_storage,
            ResourceKind.DATABASE: self._provision_database,
            ResourceKind.NETWORK: self._provision_network,
            ResourceKind.CDN: self._provision_cdn,
            ResourceKind.QUEUE: self._provision_queue,
        }
        handler = handlers.get(spec.kind)
        if handler is None:
            raise ProviderError(f"gcp cannot provision kind {spec.kind.value!r}")
        resource = handler(spec)
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
        if resource is None:
            return ResourceStatus.FAILED
        return resource.status

    def _qualified(self, kind: str, name: str) -> str:
        return f"projects/{self.project}/{kind}/{name}"

    def _provision_compute(self, spec: ResourceSpec) -> ProvisionedResource:
        serverless = bool(spec.config.get("serverless", True))
        machine = MACHINE_SIZES.get(spec.size, MACHINE_SIZES["small"])
        if serverless:
            resource_id = self._qualified("locations", f"{spec.name}/services/run")
            url = f"https://{spec.name}-hash-uc.a.run.app"
        else:
            resource_id = self._qualified(
                "zones",
                f"{self.zone}/instances/{spec.name}",
            )
            url = f"https://{self.zone}/{machine}"
        return ProvisionedResource(
            spec=spec,
            provider_id=resource_id,
            status=ResourceStatus.ACTIVE,
            endpoints=[url],
        )

    def _provision_storage(self, spec: ResourceSpec) -> ProvisionedResource:
        return ProvisionedResource(
            spec=spec,
            provider_id=self._qualified("buckets", spec.name),
            status=ResourceStatus.ACTIVE,
            endpoints=[f"https://storage.googleapis.com/{spec.name}"],
        )

    def _provision_database(self, spec: ResourceSpec) -> ProvisionedResource:
        tier = "db-f1-micro" if spec.size == "small" else "db-custom-2-7680"
        return ProvisionedResource(
            spec=spec,
            provider_id=self._qualified("instances", spec.name),
            status=ResourceStatus.ACTIVE,
            endpoints=[f"/cloudsql/{self.project}:{self.region}:{spec.name}:5432"],
        )

    def _provision_network(self, spec: ResourceSpec) -> ProvisionedResource:
        return ProvisionedResource(
            spec=spec,
            provider_id=self._qualified("global/networks", spec.name),
            status=ResourceStatus.ACTIVE,
            endpoints=[],
        )

    def _provision_cdn(self, spec: ResourceSpec) -> ProvisionedResource:
        return ProvisionedResource(
            spec=spec,
            provider_id=new_resource_id("backendService"),
            status=ResourceStatus.ACTIVE,
            endpoints=[f"https://cdn.{spec.name}.googleusercontent.com"],
        )

    def _provision_queue(self, spec: ResourceSpec) -> ProvisionedResource:
        return ProvisionedResource(
            spec=spec,
            provider_id=self._qualified("topics", spec.name),
            status=ResourceStatus.ACTIVE,
            endpoints=[f"pubsub.googleapis.com/{self.project}/topics/{spec.name}"],
        )
