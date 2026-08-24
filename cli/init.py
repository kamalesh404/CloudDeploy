"""Project scaffolding: ``clouddeploy init`` writes a starter stack file."""

from __future__ import annotations

import pathlib

import click

from src.templates import TEMPLATE_REGISTRY, available_templates

STACK_FILE = "clouddeploy.yaml"

SCAFFOLD = """\
# CloudDeploy stack definition
name: {name}
provider: {provider}
region: {region}
template: {template}

variables:
{variables}
"""

DEFAULT_VARIABLES = {
    "web-app": ("app_name", "my-app", "  app_name: my-app\n  environment: staging\n  replicas: 2"),
    "api": ("api_name", "my-api", "  api_name: my-api\n  rate_limit: 1000"),
    "static-site": ("site_name", "my-site", "  site_name: my-site\n  domain: example.com"),
    "worker": ("worker_name", "my-worker", "  worker_name: my-worker\n  concurrency: 8"),
    "microservice": (
        "service_name",
        "my-service",
        "  service_name: my-service\n  mesh_name: clouddeploy-mesh",
    ),
}


def _variables_block(template: str, name: str) -> str:
    required_key, fallback, extra = DEFAULT_VARIABLES.get(
        template,
        ("app_name", name, "  app_name: " + name),
    )
    lines = [f"  {required_key}: {name}", *extra.splitlines()[1:]]
    return "\n".join(lines)


@click.command(name="init")
@click.option(
    "--name",
    default="my-stack",
    show_default=True,
    help="Stack identifier used in state and tagging.",
)
@click.option("--provider", default="aws", show_default=True, help="Cloud provider.")
@click.option("--region", default=None, help="Provider region (provider default if omitted).")
@click.option(
    "--template",
    default="web-app",
    show_default=True,
    type=click.Choice(sorted(TEMPLATE_REGISTRY)),
    help="Deployment blueprint to scaffold.",
)
@click.option("--path", type=pathlib.Path, default=None, help="Target directory.")
def init(name: str, provider: str, region: str | None, template: str, path: pathlib.Path | None) -> None:
    """Create a new CloudDeploy project in the current directory."""

    target = path or pathlib.Path.cwd()
    stack_path = target / STACK_FILE
    if stack_path.exists():
        raise click.ClickException(f"{stack_path} already exists")

    resolved_region = region or _default_region(provider)
    content = SCAFFOLD.format(
        name=name,
        provider=provider,
        region=resolved_region,
        template=template,
        variables=_variables_block(template, name),
    )
    stack_path.write_text(content, encoding="utf-8")

    click.echo(f"Created project at {stack_path}")
    click.echo(f"Template: {template} ({TEMPLATE_REGISTRY[template].description})")
    click.echo("")
    click.echo("Next steps:")
    click.echo("  clouddeploy plan      # preview infrastructure changes")
    click.echo("  clouddeploy apply     # provision the stack")


def _default_region(provider: str) -> str:
    defaults = {
        "aws": "us-east-1",
        "gcp": "us-central1",
        "azure": "eastus",
        "digitalocean": "nyc3",
    }
    return defaults.get(provider, "us-east-1")
