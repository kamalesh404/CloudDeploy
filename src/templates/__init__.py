"""Built-in template registry and lookup helpers."""

from __future__ import annotations

from typing import TypeVar

from src.templates.api import APITemplate
from src.templates.base import Template, TemplateError
from src.templates.microservice import MicroserviceTemplate
from src.templates.static_site import StaticSiteTemplate
from src.templates.web_app import WebAppTemplate
from src.templates.worker import WorkerTemplate

TEMPLATE_REGISTRY: dict[str, Template] = {
    tpl.name: tpl
    for tpl in (
        WebAppTemplate(),
        APITemplate(),
        StaticSiteTemplate(),
        WorkerTemplate(),
        MicroserviceTemplate(),
    )
}

T = TypeVar("T", bound=Template)


def register_template(instance: T) -> T:
    """Register a custom template instance under its declared name."""

    if instance.name in TEMPLATE_REGISTRY:
        raise TemplateError(f"template {instance.name!r} is already registered")
    TEMPLATE_REGISTRY[instance.name] = instance
    return instance


def get_template(name: str) -> Template:
    """Return the registered template instance for ``name``."""

    try:
        return TEMPLATE_REGISTRY[name]
    except KeyError as exc:
        known = ", ".join(sorted(TEMPLATE_REGISTRY))
        raise TemplateError(f"unknown template {name!r}; available: {known}") from exc


def available_templates() -> list[str]:
    """Return sorted names of every registered template."""
    return sorted(TEMPLATE_REGISTRY)


__all__ = [
    "APITemplate",
    "MicroserviceTemplate",
    "StaticSiteTemplate",
    "TEMPLATE_REGISTRY",
    "Template",
    "TemplateError",
    "WebAppTemplate",
    "WorkerTemplate",
    "available_templates",
    "get_template",
    "register_template",
]
