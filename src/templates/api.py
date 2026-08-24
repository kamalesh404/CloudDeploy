"""API-only deployment template with cache and async job queue."""

from __future__ import annotations

from typing import Any

from src.providers.base import ResourceKind, ResourceSpec
from src.templates.base import Template, TemplateVariable


class APITemplate(Template):
    """Deploy a headless HTTP API without any frontend assets.

    The stack consists of a load-balanced compute tier, a Redis cache for
    hot data, and a queue that absorbs slow asynchronous work such as
    emails, exports and webhooks.
    """

    name = "api"
    description = "Load-balanced REST/GraphQL API with Redis and job queue"

    variables = [
        TemplateVariable(
            name="api_name",
            description="Short DNS-safe service identifier",
            required=True,
        ),
        TemplateVariable(
            name="auth_enabled",
            description="Attach the managed auth gateway",
            default=True,
        ),
        TemplateVariable(
            name="rate_limit",
            description="Requests per minute allowed per client",
            default=1000,
        ),
        TemplateVariable(
            name="replicas",
            description="API server replica count",
            default=3,
        ),
    ]

    def build(self, ctx: dict[str, Any]) -> list[ResourceSpec]:
        name = str(ctx["api_name"])
        replicas = int(ctx["replicas"])
        return [
            ResourceSpec(
                kind=ResourceKind.NETWORK,
                name=f"{name}-lb",
                tags={"tier": "edge", "template": self.name},
                config={"type": "load-balancer"},
            ),
            ResourceSpec(
                kind=ResourceKind.COMPUTE,
                name=f"{name}-api",
                replicas=replicas,
                size="medium" if replicas >= 5 else "small",
                tags={"tier": "app", "template": self.name},
                config={
                    "serverless": True,
                    "depends_on": [f"{name}-lb"],
                    "env": {
                        "RATE_LIMIT": str(ctx["rate_limit"]),
                        "AUTH_ENABLED": str(bool(ctx["auth_enabled"])).lower(),
                    },
                },
            ),
            ResourceSpec(
                kind=ResourceKind.DATABASE,
                name=f"{name}-cache",
                size="small",
                tags={"tier": "data", "template": self.name},
                config={"engine": "redis", "depends_on": [f"{name}-vpc"]},
            ),
            ResourceSpec(
                kind=ResourceKind.QUEUE,
                name=f"{name}-jobs",
                tags={"tier": "async", "template": self.name},
                config={"engine": "standard", "visibility_timeout": 300},
            ),
        ]
