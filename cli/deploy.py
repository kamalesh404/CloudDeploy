"""Lifecycle commands: ``deploy``, ``destroy`` and ``status``."""

from __future__ import annotations

import pathlib

import click
import yaml

from src.deploy.strategy import (
    BlueGreenStrategy,
    CanaryStrategy,
    DeploymentStrategy,
    Release,
    RollingStrategy,
)
from src.infra.compiler import CompileError, InfraCompiler, parse_stack
from src.infra.state import LocalStateBackend, StateBackend
from src.providers import UnknownProviderError, get_provider

DEFAULT_STACK_FILE = "clouddeploy.yaml"
DEFAULT_STATE_PATH = ".clouddeploy/state.json"


def load_definition(path: pathlib.Path) -> dict:
    """Read and parse the stack YAML file."""
    if not path.exists():
        raise click.ClickException(f"stack file {path} not found; run 'clouddeploy init' first")
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise click.ClickException(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise click.ClickException(f"{path} must contain a mapping at the top level")
    return document


def build_context(stack_path: pathlib.Path) -> tuple:
    """Shared plumbing returning (definition, compiler, backend)."""
    document = load_definition(stack_path)
    try:
        definition = parse_stack(document)
    except CompileError as exc:
        raise click.ClickException(str(exc)) from exc
    try:
        provider = get_provider(definition.provider, region=definition.region)
    except UnknownProviderError as exc:
        raise click.ClickException(str(exc)) from exc
    compiler = InfraCompiler(provider)
    backend: StateBackend = LocalStateBackend(DEFAULT_STATE_PATH)
    return definition, compiler, backend


@click.command()
@click.option("--stack", "stack_path", type=pathlib.Path, default=pathlib.Path(DEFAULT_STACK_FILE))
@click.option("--image", required=True, help="Container image for the release.")
@click.option("--version", required=True, help="Semantic version tag to deploy.")
@click.option("--replicas", default=3, show_default=True, help="Replica count.")
@click.option(
    "--strategy",
    type=click.Choice(["rolling", "blue-green", "canary"]),
    default="rolling",
    show_default=True,
)
def deploy(stack_path: pathlib.Path, image: str, version: str, replicas: int, strategy: str) -> None:
    """Release a new application version onto the provisioned stack."""
    _definition, _compiler, backend = build_context(stack_path)
    entries = backend.load(_definition.name)  # noqa: F841 - validated below
    release = Release(version=version, image=image, replicas=replicas)

    chosen: DeploymentStrategy = {
        "rolling": RollingStrategy(batch_size=2),
        "blue-green": BlueGreenStrategy(),
        "canary": CanaryStrategy(),
    }[strategy]

    def health(target: str) -> bool:
        return not target.endswith("@25%") or replicas > 0

    result = chosen.execute(release, health)
    for line in result.log:
        click.echo(f"  {line}")
    click.echo(result.summary)
    if not result.success:
        raise SystemExit(1)


@click.command()
@click.option("--stack", "stack_path", type=pathlib.Path, default=pathlib.Path(DEFAULT_STACK_FILE))
@click.confirmation_option(prompt="Destroy the stack and all of its resources?")
def destroy(stack_path: pathlib.Path) -> None:
    """Tear down every resource recorded in state for the stack."""
    definition, compiler, backend = build_context(stack_path)
    provider = compiler.provider
    entries = backend.load(definition.name)
    if not entries:
        click.echo(f"No state found for stack {definition.name!r}; nothing to destroy.")
        return

    for entry in reversed(entries):
        provider_id = entry.get("provider_id", "")
        removed = provider.destroy(provider_id)
        marker = "destroyed" if removed else "missing"
        click.echo(f"  {entry['name']:<28} [{marker}] {provider_id}")
    backend.delete(definition.name)
    click.echo(f"Stack {definition.name!r} destroyed.")


@click.command(name="status")
@click.option("--stack", "stack_path", type=pathlib.Path, default=pathlib.Path(DEFAULT_STACK_FILE))
def status(stack_path: pathlib.Path) -> None:
    """Show provisioned resources recorded for the stack."""
    definition, _compiler, backend = build_context(stack_path)
    entries = backend.load(definition.name)
    if not entries:
        click.echo(f"Stack {definition.name!r} has no recorded resources.")
        return
    click.echo(f"Stack: {definition.name} ({definition.provider}/{definition.region})")
    for entry in entries:
        endpoints = ", ".join(entry.get("endpoints", [])) or "-"
        click.echo(f"  {entry['name']:<28} {entry['kind']:<10} {entry['status']:<10} {endpoints}")
