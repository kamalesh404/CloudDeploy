"""Click entry point wiring every command group into the ``clouddeploy`` app."""

from __future__ import annotations

import click

from src import __version__
from src.deploy import preview as _preview  # noqa: F401
from cli.deploy import deploy, destroy, status
from cli.infra import apply, diff, plan
from cli.init import init
from cli.monitor import alerts, logs, metrics


@click.group(help="CloudDeploy: ship cloud applications in minutes.")
@click.version_option(__version__, prog_name="clouddeploy")
def cli() -> None:
    """Top-level command group; subcommands attach below."""


cli.add_command(init)
cli.add_command(plan)
cli.add_command(apply)
cli.add_command(diff)
cli.add_command(deploy)
cli.add_command(destroy)
cli.add_command(status)
cli.add_command(logs)
cli.add_command(metrics)
cli.add_command(alerts)

main = cli


if __name__ == "__main__":
    cli()
