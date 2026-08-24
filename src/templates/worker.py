"""Background worker template: queue-driven processing fleet."""

from __future__ import annotations

from typing import Any

from src.providers.base import ResourceKind, ResourceSpec
from src.templates.base import Template, TemplateVariable


class WorkerTemplate(Template):
    """Deploy a horizontally scaled worker pool consuming a managed queue.

    Workers pull jobs from the queue, write large artefacts to object
    storage and publish progress back to the application tier. Autoscaling
    is driven by queue depth so idle fleets cost almost nothing.
    """

    name = "worker"
    description = "Queue-backed background workers with autoscaling"

    variables = [
        TemplateVariable(
            name="worker_name",
            description="Short DNS-safe worker identifier",
            required=True,
        ),
        TemplateVariable(
            name="concurrency",
            description="Jobs processed in parallel per replica",
            default=8,
        ),
        TemplateVariable(
            name="max_queue_depth",
            description="Queue depth that triggers scale-out",
            default=500,
        ),
        TemplateVariable(
            name="replicas",
            description="Baseline worker replicas",
            default=3,
        ),
    ]

    def build(self, ctx: dict[str, Any]) -> list[ResourceSpec]:
        name = str(ctx["worker_name"])
        return [
            ResourceSpec(
                kind=ResourceKind.QUEUE,
                name=f"{name}-tasks",
                tags={"tier": "async", "template": self.name},
                config={
                    "engine": "fifo",
                    "max_queue_depth": int(ctx["max_queue_depth"]),
                    "visibility_timeout": 900,
                    "dead_letter": f"{name}-dlq",
                },
            ),
            ResourceSpec(
                kind=ResourceKind.COMPUTE,
                name=f"{name}-pool",
                replicas=int(ctx["replicas"]),
                size="medium",
                tags={"tier": "worker", "template": self.name},
                config={
                    "serverless": False,
                    "depends_on": [f"{name}-tasks"],
                    "autoscaling": {
                        "metric": "queue_depth",
                        "target": int(ctx["max_queue_depth"]),
                    },
                    "env": {"CONCURRENCY": str(ctx["concurrency"])},
                },
            ),
            ResourceSpec(
                kind=ResourceKind.STORAGE,
                name=f"{name}-artifacts",
                tags={"tier": "data", "template": self.name},
                config={
                    "lifecycle_days": 30,
                    "versioning": False,
                },
            ),
        ]
