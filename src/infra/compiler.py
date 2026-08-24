"""Stack definition parsing and the YAML-to-resources compiler."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from src.providers.base import CloudProvider, ProvisionedResource, ProviderError
from src.providers.base import ResourceKind, ResourceSpec
from src.templates import TemplateError, get_template
from src.templates.base import Template

STACK_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{2,30}$")

REQUIRED_KEYS = ("name", "provider")


class CompileError(ProviderError):
    """Raised when a stack document cannot be compiled into resource specs."""


@dataclass(slots=True)
class StackDefinition:
    """Parsed representation of a ``clouddeploy.yaml`` document."""

    name: str
    provider: str
    region: str = "us-east-1"
    template: str | None = None
    variables: dict[str, Any] = field(default_factory=dict)
    resources: list[dict[str, Any]] = field(default_factory=list)

    def uses_template(self) -> bool:
        return self.template is not None


def parse_stack(document: dict[str, Any]) -> StackDefinition:
    """Validate raw YAML input and coerce it into a :class:`StackDefinition`."""

    if not isinstance(document, dict):
        raise CompileError("stack document must be a mapping")
    missing = [key for key in REQUIRED_KEYS if key not in document]
    if missing:
        raise CompileError(f"stack is missing required keys: {', '.join(missing)}")

    name = str(document["name"])
    if not STACK_NAME_PATTERN.match(name):
        raise CompileError(
            f"stack name {name!r} must match {STACK_NAME_PATTERN.pattern}",
        )

    resources = document.get("resources") or []
    if not isinstance(resources, list):
        raise CompileError("'resources' must be a list of resource mappings")

    return StackDefinition(
        name=name,
        provider=str(document["provider"]),
        region=str(document.get("region", "us-east-1")),
        template=document.get("template"),
        variables=dict(document.get("variables") or {}),
        resources=[dict(item) for item in resources],
    )


class InfraCompiler:
    """Turn a :class:`StackDefinition` into provisionable resource specs.

    The compiler resolves templates (or inline resources), applies stack-wide
    tags and the target region, then hands specs to the provider for apply.
    """

    def __init__(
        self,
        provider: CloudProvider,
        default_tags: dict[str, str] | None = None,
    ) -> None:
        self.provider = provider
        self.default_tags = default_tags or {}

    def compile(self, definition: StackDefinition) -> list[ResourceSpec]:
        """Produce ordered resource specs from a parsed stack definition."""

        template = self._resolve_template(definition)
        if template is not None:
            specs = template.render(definition.variables)
        else:
            specs = [self._spec_from_resource(r) for r in definition.resources]

        if not specs:
            raise CompileError(f"stack {definition.name!r} produced no resources")

        tagged = []
        for spec in specs:
            spec.region = definition.region
            spec.tags.update(
                {
                    **self.default_tags,
                    "stack": definition.name,
                    "template": definition.template or "custom",
                },
            )
            tagged.append(spec)
        return tagged

    def apply(self, specs: list[ResourceSpec]) -> list[ProvisionedResource]:
        """Validate then provision every spec; abort on the first failure."""

        provisioned: list[ProvisionedResource] = []
        for spec in specs:
            errors = self.provider.validate_spec(spec)
            if errors:
                raise CompileError(
                    f"invalid resource {spec.name!r}: {'; '.join(errors)}",
                )
            try:
                provisioned.append(self.provider.provision(spec))
            except ProviderError as exc:
                raise CompileError(
                    f"failed to provision {spec.name!r}: {exc}",
                ) from exc
        return provisioned

    def _resolve_template(self, definition: StackDefinition) -> Template | None:
        if not definition.uses_template():
            return None
        if definition.template and not definition.variables:
            raise TemplateError(
                f"template {definition.template!r} declared without variables",
            )
        assert definition.template is not None
        return get_template(definition.template)

    def _spec_from_resource(self, raw: dict[str, Any]) -> ResourceSpec:
        try:
            kind = ResourceKind(str(raw["kind"]))
            name = str(raw["name"])
        except KeyError as exc:
            raise CompileError(f"resource entry missing key {exc}") from exc
        except ValueError as exc:
            raise CompileError(f"unknown resource kind in {raw!r}") from exc

        config = dict(raw.get("config") or {})
        depends_on = raw.get("depends_on")
        if depends_on:
            config["depends_on"] = list(depends_on)

        return ResourceSpec(
            kind=kind,
            name=name,
            size=str(raw.get("size", "small")),
            replicas=int(raw.get("replicas", 1)),
            tags={str(k): str(v) for k, v in (raw.get("tags") or {}).items()},
            config=config,
        )
