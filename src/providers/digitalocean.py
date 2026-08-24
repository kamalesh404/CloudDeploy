"""DigitalOcean provider covering Droplets, App Platform, Managed DB and Spaces."""

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

DROPLET_SIZES: dict[str, str] = {
    "micro": "s-1vcpu-1gb",
    "small": "s-1vcpu-2gb",
    "medium": "s-2vcpu-4gb",
    "large": "s-4vcpu-8gb",
    "xlarge": "c-8",
}

SUPPORTED_REGIONS = frozenset({"nyc1", "nyc3", "sfo3", "ams3", "sgp1", "lon1"})


class DigitalOceanProvider(CloudProvider):
    """Provision DigitalOcean resources with slug-based sizing."""

    name = "digitalocean"
    display_name = "DigitalOcean"

    def __init__(self, region: str = "nyc3", **kwargs: Any) -> None:
        super().__init__(region=region, **kwargs)
        if region not in SUPPORTED_REGIONS:
            raise ProviderError(f"unsupported DigitalOcean region {region!r}")

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
        """Provision a resource using the App Platform or Droplet pipeline."""
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
            raise ProviderError(
                f"digitalocean cannot provision kind {spec.kind.value!r}",
            )
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

    def _provision_compute(self, spec: ResourceSpec) -> ProvisionedResource:
        platform = spec.config.get("platform", "app-platform")
        if platform == "droplet":
            slug = DROPLET_SIZES.get(spec.size, DROPLET_SIZES["small"])
            droplet_id = str(abs(hash((slug, spec.name))) % 9_000_000 + 1_000_000)
            endpoint = f"{spec.name}.{self.region}.droplets.digitalocean.com"
        else:
            droplet_id = new_resource_id("app")
            endpoint = f"https://{spec.name}.ondigitalocean.app"
        return ProvisionedResource(
            spec=spec,
            provider_id=droplet_id,
            status=ResourceStatus.ACTIVE,
            endpoints=[endpoint],
        )

    def _provision_storage(self, spec: ResourceSpec) -> ProvisionedResource:
        return ProvisionedResource(
            spec=spec,
            provider_id=f"spaces://{spec.name}",
            status=ResourceStatus.ACTIVE,
            endpoints=[f"https://{spec.name}.{self.region}.digitaloceanspaces.com"],
        )

    def _provision_database(self, spec: ResourceSpec) -> ProvisionedResource:
        engine = spec.config.get("engine", "pg")
        db_id = new_resource_id(engine)
        port = 25061 if engine == "pg" else 3306
        return ProvisionedResource(
            spec=spec,
            provider_id=db_id,
            status=ResourceStatus.ACTIVE,
            endpoints=[f"{spec.name}-db.b.db.ondigitalocean.com:{port}"],
        )

    def _provision_network(self, spec: ResourceSpec) -> ProvisionedResource:
        return ProvisionedResource(
            spec=spec,
            provider_id=new_resource_id("vpc"),
            status=ResourceStatus.ACTIVE,
            endpoints=[],
        )

    def _provision_cdn(self, spec: ResourceSpec) -> ProvisionedResource:
        return ProvisionedResource(
            spec=spec,
            provider_id=new_resource_id("cdn"),
            status=ResourceStatus.ACTIVE,
            endpoints=[f"https://{spec.name}.cdn.digitaloceanspaces.com"],
        )

    def _provision_queue(self, spec: ResourceSpec) -> ProvisionedResource:
        return ProvisionedResource(
            spec=spec,
            provider_id=new_resource_id("queue"),
            status=ResourceStatus.ACTIVE,
            endpoints=[f"https://queue.{self.region}.digitalocean.com/{spec.name}"],
        )
