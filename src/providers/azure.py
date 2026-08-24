"""Microsoft Azure provider covering Virtual Machines, App Service, SQL and Blob."""

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

VM_SIZES: dict[str, str] = {
    "micro": "Standard_B1s",
    "small": "Standard_B2s",
    "medium": "Standard_D2s_v5",
    "large": "Standard_D8s_v5",
    "xlarge": "Standard_F16s_v2",
}

SUPPORTED_REGIONS = frozenset(
    {"eastus", "westeurope", "southeastasia", "centralus"},
)


class AzureProvider(CloudProvider):
    """Manage Azure resources inside a dedicated resource group per stack."""

    name = "azure"
    display_name = "Microsoft Azure"

    def __init__(
        self,
        region: str = "eastus",
        subscription_id: str = "00000000-0000-0000-0000-000000000000",
        resource_group: str = "clouddeploy-rg",
        **kwargs: Any,
    ) -> None:
        super().__init__(region=region, **kwargs)
        if region not in SUPPORTED_REGIONS:
            raise ProviderError(f"unsupported Azure region {region!r}")
        self.subscription_id = subscription_id
        self.resource_group = resource_group

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
        """Provision a resource and register it under the resource group."""
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
            raise ProviderError(f"azure cannot provision kind {spec.kind.value!r}")
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

    def _arm_id(self, provider_namespace: str, kind: str, name: str) -> str:
        return (
            f"/subscriptions/{self.subscription_id}"
            f"/resourceGroups/{self.resource_group}"
            f"/providers/{provider_namespace}/{kind}/{name}"
        )

    def _provision_compute(self, spec: ResourceSpec) -> ProvisionedResource:
        plan = spec.config.get("plan", "app-service")
        vm_size = VM_SIZES.get(spec.size, VM_SIZES["small"])
        if plan == "vm":
            resource_id = self._arm_id("Microsoft.Compute", "virtualMachines", spec.name)
            endpoint = f"{spec.name}.{self.region}.cloudapp.azure.com"
        else:
            resource_id = self._arm_id("Microsoft.Web", "sites", spec.name)
            endpoint = f"https://{spec.name}.azurewebsites.net"
        return ProvisionedResource(
            spec=spec,
            provider_id=resource_id,
            status=ResourceStatus.ACTIVE,
            endpoints=[endpoint],
        )

    def _provision_storage(self, spec: ResourceSpec) -> ProvisionedResource:
        account = spec.name.replace("-", "")[:24]
        return ProvisionedResource(
            spec=spec,
            provider_id=self._arm_id("Microsoft.Storage", "storageAccounts", account),
            status=ResourceStatus.ACTIVE,
            endpoints=[f"https://{account}.blob.core.windows.net"],
        )

    def _provision_database(self, spec: ResourceSpec) -> ProvisionedResource:
        return ProvisionedResource(
            spec=spec,
            provider_id=self._arm_id("Microsoft.Sql", "servers/databases", spec.name),
            status=ResourceStatus.ACTIVE,
            endpoints=[
                f"{spec.name}.database.windows.net:1433?tier={spec.size}",
            ],
        )

    def _provision_network(self, spec: ResourceSpec) -> ProvisionedResource:
        return ProvisionedResource(
            spec=spec,
            provider_id=self._arm_id("Microsoft.Network", "vnets", spec.name),
            status=ResourceStatus.ACTIVE,
            endpoints=[],
        )

    def _provision_cdn(self, spec: ResourceSpec) -> ProvisionedResource:
        profile = new_resource_id("profile")
        return ProvisionedResource(
            spec=spec,
            provider_id=self._arm_id("Microsoft.Cdn", "profiles", profile),
            status=ResourceStatus.ACTIVE,
            endpoints=[f"https://{spec.name}-{self.region}.azureedge.net"],
        )

    def _provision_queue(self, spec: ResourceSpec) -> ProvisionedResource:
        namespace = f"sb-{spec.name}".replace("-", "")[:20]
        return ProvisionedResource(
            spec=spec,
            provider_id=self._arm_id("Microsoft.ServiceBus", "namespaces", namespace),
            status=ResourceStatus.ACTIVE,
            endpoints=[f"https://{namespace}.servicebus.windows.net"],
        )
