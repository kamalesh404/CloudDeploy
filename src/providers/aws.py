"""Amazon Web Services provider covering EC2, ECS, Lambda, S3, RDS and CloudFront."""

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

INSTANCE_SIZES: dict[str, str] = {
    "micro": "t3.micro",
    "small": "t3.small",
    "medium": "m5.large",
    "large": "m5.xlarge",
    "xlarge": "c5.4xlarge",
}

SUPPORTED_REGIONS = frozenset(
    {"us-east-1", "us-west-2", "eu-west-1", "eu-central-1", "ap-southeast-1"},
)


class AWSProvider(CloudProvider):
    """Provision AWS resources by translating specs into service calls.

    The implementation is intentionally provider-shaped: each resource kind
    maps to one private method that mirrors the real AWS API call, so the
    class can be backed by botocore without changing callers.
    """

    name = "aws"
    display_name = "Amazon Web Services"

    def __init__(self, region: str = "us-east-1", **kwargs: Any) -> None:
        super().__init__(region=region, **kwargs)
        if region not in SUPPORTED_REGIONS:
            raise ProviderError(f"unsupported AWS region {region!r}")

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
        """Dispatch the spec to the matching AWS service handler."""
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
            raise ProviderError(f"aws cannot provision kind {spec.kind.value!r}")
        resource = handler(spec)
        self._resources[resource.provider_id] = resource
        return resource

    def destroy(self, provider_id: str) -> bool:
        """Mark an AWS resource as destroyed; unknown ids are ignored."""
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
        engine = spec.config.get("engine", "ecs")
        instance_type = INSTANCE_SIZES.get(spec.size, INSTANCE_SIZES["small"])
        if engine == "lambda":
            resource_id = new_resource_id("arn:aws:lambda")
        else:
            resource_id = new_resource_id("i")
        return ProvisionedResource(
            spec=spec,
            provider_id=resource_id,
            status=ResourceStatus.ACTIVE,
            endpoints=[f"{spec.name}.{self.region}.ecs.amazonaws.com"],
        )

    def _provision_storage(self, spec: ResourceSpec) -> ProvisionedResource:
        return ProvisionedResource(
            spec=spec,
            provider_id=f"arn:aws:s3:::{spec.name}",
            status=ResourceStatus.ACTIVE,
            endpoints=[f"https://{spec.name}.s3.amazonaws.com"],
        )

    def _provision_database(self, spec: ResourceSpec) -> ProvisionedResource:
        return ProvisionedResource(
            spec=spec,
            provider_id=new_resource_id("db"),
            status=ResourceStatus.ACTIVE,
            endpoints=[f"{spec.name}.cluster-{self.region}.rds.amazonaws.com:5432"],
        )

    def _provision_network(self, spec: ResourceSpec) -> ProvisionedResource:
        return ProvisionedResource(
            spec=spec,
            provider_id=new_resource_id("vpc"),
            status=ResourceStatus.ACTIVE,
            endpoints=[],
        )

    def _provision_cdn(self, spec: ResourceSpec) -> ProvisionedResource:
        distribution = new_resource_id("E")
        return ProvisionedResource(
            spec=spec,
            provider_id=distribution.upper(),
            status=ResourceStatus.ACTIVE,
            endpoints=[f"https://{distribution.lower()}.cloudfront.net"],
        )

    def _provision_queue(self, spec: ResourceSpec) -> ProvisionedResource:
        return ProvisionedResource(
            spec=spec,
            provider_id=f"arn:aws:sqs:{self.region}:000000000000:{spec.name}",
            status=ResourceStatus.ACTIVE,
            endpoints=[f"https://sqs.{self.region}.amazonaws.com/{spec.name}"],
        )
