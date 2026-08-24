"""Provider registry and factory for supported cloud backends."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from src.providers.azure import AzureProvider
from src.providers.base import CloudProvider, ProviderError
from src.providers.digitalocean import DigitalOceanProvider
from src.providers.aws import AWSProvider
from src.providers.gcp import GCPProvider

PROVIDER_REGISTRY: dict[str, type[CloudProvider]] = {
    AWSProvider.name: AWSProvider,
    GCPProvider.name: GCPProvider,
    AzureProvider.name: AzureProvider,
    DigitalOceanProvider.name: DigitalOceanProvider,
}

P = TypeVar("P", bound=type[CloudProvider])


class UnknownProviderError(ProviderError):
    """Raised when a stack references a provider that is not registered."""


def register_provider(cls: P) -> P:
    """Class decorator that adds a provider implementation to the registry."""

    if cls.name in PROVIDER_REGISTRY:
        raise ProviderError(f"provider {cls.name!r} is already registered")
    PROVIDER_REGISTRY[cls.name] = cls
    return cls


def get_provider(name: str, **kwargs: Any) -> CloudProvider:
    """Instantiate a registered provider by name with constructor options."""

    try:
        provider_cls = PROVIDER_REGISTRY[name]
    except KeyError as exc:
        known = ", ".join(sorted(PROVIDER_REGISTRY))
        raise UnknownProviderError(
            f"unknown provider {name!r}; available providers: {known}",
        ) from exc
    return provider_cls(**kwargs)


def available_providers() -> list[str]:
    """Return the sorted list of registered provider names."""
    return sorted(PROVIDER_REGISTRY)


__all__ = [
    "AWSProvider",
    "AzureProvider",
    "CloudProvider",
    "DigitalOceanProvider",
    "GCPProvider",
    "PROVIDER_REGISTRY",
    "ProviderError",
    "UnknownProviderError",
    "available_providers",
    "get_provider",
    "register_provider",
]
