"""Infrastructure commands: ``plan``, ``apply`` and ``diff``."""

from __future__ import annotations

import pathlib
import sys

import click

from cli.deploy import DEFAULT_STACK_FILE, build_context
from src.infra.diff import Action, compute_plan


def _plan(stack_path: pathlib.Path):
    definition, compiler, backend = build_context(stack_path)
    desired = compiler.compile(definition)
    state_entries = backend.load(definition.name)
    return definition, compute_plan(definition.name, desired, state_entries)


def _echo_plan(plan) -> None:  # noqa: ANN001 - Plan type kept loose for CLI layer
    icons = {
        Action.CREATE: "+",
        Action.UPDATE: "~",
        Action.DELETE: "-",
        Action.NOOP: "=",
    }
    colors = {
        Action.CREATE: "green",
        Action.UPDATE: "yellow",
        Action.DELETE: "red",
        Action.NOOP: "white",
    }
    for change in plan.changes:
        icon = icons[change.action]
        color = colors[change.action]
        detail = ""
        if change.action is Action.UPDATE:
            before = change.before or {}
            after = change.after or {}
            fields = [
                key
                for key in ("region", "size", "replicas", "tags", "config")
                if before.get(key) != after.get(key)
            ]
            detail = f" (changed: {', '.join(fields)})"
        elif change.action is Action.CREATE and change.after is not None:
            detail = f" ({change.after['kind']})"
        click.secho(f"  {icon} {change.name}{detail}", fg=color)
    click.echo("")
    color = "green" if plan.is_empty else "yellow"
    click.secho(plan.summary(), fg=color)


@click.command()
@click.option("--stack", "stack_path", type=pathlib.Path, default=pathlib.Path(DEFAULT_STACK_FILE))
@click.option("--detailed", is_flag=True, help="Print full before/after payloads.")
def plan(stack_path: pathlib.Path, detailed: bool) -> None:
    """Preview the changes apply would make, without touching the cloud."""
    _definition, infra_plan = _plan(stack_path)
    _echo_plan(infra_plan)
    if detailed:
        for change in infra_plan.changes:
            if change.action is not Action.NOOP:
                click.echo(f"{change.name}: {change.action.value}")
                if change.before:
                    click.echo(f"  before: {change.before}")
                if change.after:
                    click.echo(f"  after:  {change.after}")
    if not infra_plan.is_empty:
        raise SystemExit(2)


@click.command()
@click.option("--stack", "stack_path", type=pathlib.Path, default=pathlib.Path(DEFAULT_STACK_FILE))
@click.option("--auto-approve", is_flag=True, help="Skip the interactive confirmation.")
def apply(stack_path: pathlib.Path, auto_approve: bool) -> None:
    """Compile the stack and provision any pending resources."""
    definition, compiler, backend = _context_with_plan_check(stack_path)
    desired = compiler.compile(definition)

    if not auto_approve:
        click.confirm(f"Apply stack {definition.name!r}?", abort=True)

    provisioned = compiler.apply(desired)
    backend.save(definition.name, provisioned)
    for resource in provisioned:
        endpoints = ", ".join(resource.endpoints) or "-"
        click.secho(f"  + {resource.spec.name:<28} {resource.provider_id}", fg="green")
        click.echo(f"      {endpoints}")
    click.echo(f"Applied {len(provisioned)} resources to {definition.name!r}.")


def _context_with_plan_check(stack_path: pathlib.Path):
    """Build context while surfacing compile errors as clean CLI failures."""
    from src.infra.compiler import CompileError

    try:
        return build_context(stack_path)
    except CompileError as exc:
        raise click.ClickException(str(exc)) from exc


@click.command(name="diff")
@click.option("--stack", "stack_path", type=pathlib.Path, default=pathlib.Path(DEFAULT_STACK_FILE))
def diff(stack_path: pathlib.Path) -> None:
    """Show drift between live state and configuration; exits 2 on drift."""
    _definition, infra_plan = _plan(stack_path)
    if infra_plan.is_empty:
        click.echo("No drift detected. Infrastructure matches configuration.")
        return
    _echo_plan(infra_plan)
    sys.exit(2)
