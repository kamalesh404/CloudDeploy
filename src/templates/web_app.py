"""Full-stack web application template: frontend assets, API tier and database."""

from __future__ import annotations

from typing import Any

from src.providers.base import ResourceKind, ResourceSpec
from src.templates.base import Template, TemplateVariable


class WebAppTemplate(Template):
    """Deploy a classic three-tier web application.

    The blueprint wires a VPC-style network, a load-balanced compute tier,
    a managed PostgreSQL database, an asset bucket and a CDN in front of
    everything — the shape most customer-facing products need.
    """

    name = "web-app"
    description = "Frontend + backend + PostgreSQL with CDN asset delivery"

    variables = [
        TemplateVariable(
            name="app_name",
            description="Short DNS-safe application identifier",
            required=True,
        ),
        TemplateVariable(
            name="environment",
            description="Deployment environment label",
            default="staging",
            choices=("development", "staging", "production"),
        ),
        TemplateVariable(
            name="replicas",
            description="Number of web server instances",
            default=2,
        ),
        TemplateVariable(
            name="db_size",
            description="Database instance size class",
            default="small",
            choices=("small", "medium", "large"),
        ),
    ]

    def build(self, ctx: dict[str, Any]) -> list[ResourceSpec]:
        app = str(ctx["app_name"])
        replicas = int(ctx["replicas"])
        env_tag = {
            "environment": str(ctx["environment"]),
            "template": self.name,
        }
        return [
            ResourceSpec(
                kind=ResourceKind.NETWORK,
                name=f"{app}-vpc",
                tags={"tier": "network", **env_tag},
            ),
            ResourceSpec(
                kind=ResourceKind.COMPUTE,
                name=f"{app}-web",
                replicas=replicas,
                size="medium" if ctx["environment"] == "production" else "small",
                tags={"tier": "web", **env_tag},
                config={"engine": "ecs", "depends_on": [f"{app}-vpc"]},
            ),
            ResourceSpec(
                kind=ResourceKind.DATABASE,
                name=f"{app}-db",
                size=str(ctx["db_size"]),
                tags={"tier": "data", **env_tag},
                config={"engine": "postgres", "depends_on": [f"{app}-vpc"]},
            ),
            ResourceSpec(
                kind=ResourceKind.STORAGE,
                name=f"{app}-assets",
                tags={"tier": "assets", **env_tag},
            ),
            ResourceSpec(
                kind=ResourceKind.CDN,
                name=f"{app}-cdn",
                tags={"tier": "edge", **env_tag},
                config={"origin": f"{app}-assets", "depends_on": [f"{app}-assets"]},
            ),
        ]
