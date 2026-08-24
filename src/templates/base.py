"""Template engine: variable resolution and the abstract Template contract."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

VARIABLE_PATTERN = re.compile(r"\$\{([a-z_][a-z0-9_]*)\}")


class TemplateError(Exception):
    """Raised when template variables are missing or invalid."""


@dataclass(frozen=True, slots=True)
class TemplateVariable:
    """A single declared input for a deployment template."""

    name: str
    description: str = ""
    default: Any = None
    required: bool = False
    choices: tuple[Any, ...] | None = None


def substitute(text: str, context: dict[str, Any]) -> str:
    """Replace ``${name}`` placeholders in text with values from context.

    Unknown variables are left untouched so partial rendering is possible,
    while missing-but-required inputs are caught earlier by resolution.
    """

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = context.get(key)
        return str(value) if value is not None else match.group(0)

    return VARIABLE_PATTERN.sub(_replace, text)


class Template(ABC):
    """Base class every deployment blueprint must extend.

    Subclasses declare their inputs via :attr:`variables` and implement
    :meth:`build`, which receives fully resolved variables and returns a
    list of resource specs ready for compilation.
    """

    name: ClassVar[str] = "abstract"
    description: ClassVar[str] = ""

    variables: ClassVar[list[TemplateVariable]] = []

    def resolve_variables(self, provided: dict[str, Any]) -> dict[str, Any]:
        """Merge user input with declared defaults and validate everything."""

        resolved: dict[str, Any] = {}
        for var in self.variables:
            if var.name in provided:
                value = provided[var.name]
            elif var.required:
                raise TemplateError(
                    f"template {self.name!r} requires variable {var.name!r}",
                )
            else:
                value = var.default

            if var.choices is not None and value not in var.choices:
                options = ", ".join(str(c) for c in var.choices)
                raise TemplateError(
                    f"variable {var.name!r} must be one of: {options}",
                )
            resolved[var.name] = value
        return resolved

    @abstractmethod
    def build(self, ctx: dict[str, Any]) -> list[Any]:
        """Construct the resource specs this template represents."""

    def render(self, provided: dict[str, Any] | None = None) -> list[Any]:
        """Resolve variables then delegate to :meth:`build`."""
        return self.build(self.resolve_variables(provided or {}))

    def describe(self) -> dict[str, Any]:
        """Return a JSON-serialisable summary used by ``clouddeploy init``."""
        return {
            "name": self.name,
            "description": self.description,
            "variables": [
                {
                    "name": v.name,
                    "description": v.description,
                    "default": v.default,
                    "required": v.required,
                }
                for v in self.variables
            ],
        }
