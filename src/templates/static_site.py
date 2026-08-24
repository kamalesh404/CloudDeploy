"""Static site template: object storage origin with a global CDN in front."""

from __future__ import annotations

from typing import Any

from src.providers.base import ResourceKind, ResourceSpec
from src.templates.base import Template, TemplateVariable


class StaticSiteTemplate(Template):
    """Deploy a static site or SPA for a few cents a month.

    Only two resources are needed: a versioned storage bucket holding the
    built assets and a CDN distribution that terminates TLS, gzips on the
    edge and serves the closest point of presence to each visitor.
    """

    name = "static-site"
    description = "Bucket + CDN hosting for static sites and SPAs"

    variables = [
        TemplateVariable(
            name="site_name",
            description="Short DNS-safe bucket/site identifier",
            required=True,
        ),
        TemplateVariable(
            name="domain",
            description="Custom domain served by the CDN",
            default="example.com",
        ),
        TemplateVariable(
            name="spa_mode",
            description="Rewrite all paths to index.html",
            default=True,
        ),
    ]

    def build(self, ctx: dict[str, Any]) -> list[ResourceSpec]:
        site = str(ctx["site_name"])
        return [
            ResourceSpec(
                kind=ResourceKind.STORAGE,
                name=f"{site}-site",
                tags={"tier": "origin", "template": self.name},
                config={
                    "versioning": True,
                    "spa_mode": bool(ctx["spa_mode"]),
                    "index_document": "index.html",
                    "error_document": "404.html",
                },
            ),
            ResourceSpec(
                kind=ResourceKind.CDN,
                name=f"{site}-cdn",
                tags={"tier": "edge", "template": self.name},
                config={
                    "origin": f"{site}-site",
                    "domain": str(ctx["domain"]),
                    "default_ttl": 3600,
                    "depends_on": [f"{site}-site"],
                },
            ),
        ]
