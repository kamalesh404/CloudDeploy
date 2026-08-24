"""Deployment strategy, rollback and preview environment tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.deploy.preview import PreviewEnvironment, PreviewManager, slugify
from src.deploy.rollback import HealthGate, RollbackError, RollbackManager
from src.deploy.strategy import (
    BlueGreenStrategy,
    CanaryStrategy,
    DeploymentStrategy,
    Release,
    RollingStrategy,
)
from tests.conftest import FakeProvider


def healthy(_: str) -> bool:
    return True


def test_rolling_deploys_in_batches_and_succeeds(release: Release) -> None:
    strategy = RollingStrategy(batch_size=2)
    result = strategy.execute(release, healthy)

    assert result.success is True
    assert result.healthy_replicas == 3
    assert result.log[0].startswith("batch 1/2")
    assert any("healthy (2/3)" in line for line in result.log)


def test_rolling_aborts_on_unhealthy_batch(release: Release) -> None:
    def flaky(target: str) -> bool:
        return not target.endswith(":1")

    result = RollingStrategy(batch_size=1).execute(release, flaky)

    assert result.success is False
    assert "aborting" in result.log[-1]
    assert result.message.startswith("unhealthy batch")


def test_blue_green_switches_traffic_atomically(release: Release) -> None:
    result = BlueGreenStrategy().execute(release, healthy)

    assert result.success is True
    assert "switching traffic to green" in result.log
    assert any("draining blue" in line for line in result.log)


def test_canary_walks_weights_and_promotes(release: Release) -> None:
    seen: list[str] = []

    def tracking(target: str) -> bool:
        seen.append(target)
        return True

    result = CanaryStrategy(weights=(5, 50, 100)).execute(release, tracking)

    assert result.success is True
    assert [target for target in seen] == ["v2.0.0@5%", "v2.0.0@50%", "v2.0.0@100%"]
    assert result.message == "canary promoted to 100%"


def test_canary_fails_fast_at_gate(release: Release) -> None:
    def breaks_at_twenty_five(target: str) -> bool:
        return target != "v2.0.0@25%"

    result = CanaryStrategy().execute(release, breaks_at_twenty_five)

    assert result.success is False
    assert result.message == "canary aborted at 25%"
    assert "shifting 5%" in result.log and "shifting 50%" not in result.log


def test_canary_rejects_invalid_weights() -> None:
    with pytest.raises(ValueError):
        CanaryStrategy(weights=(10, 40))


def test_health_gate_requires_consecutive_passes() -> None:
    attempts: list[str] = []

    def passing(target: str) -> bool:
        attempts.append(target)
        return True

    gate = HealthGate(check=passing, min_passes=3)
    assert gate.passes("green:v9") is True
    assert len(attempts) == 3

    failing_gate = HealthGate(check=lambda _: False, min_passes=2)
    assert failing_gate.passes("green:v9") is False


def test_rollback_manager_redploys_previous_stable() -> None:
    manager = RollbackManager()
    manager.record("v1", image="shop:v1", replicas=3, success=True)
    manager.record("v2", image="shop:v2", replicas=3, success=True)
    strategy: DeploymentStrategy = BlueGreenStrategy()

    result = manager.rollback_to_previous(
        failed_version="v2",
        strategy=strategy,
        health=healthy,
    )

    assert result.version == "v1"
    assert manager.history[-1].version == "v1"


def test_rollback_without_history_raises() -> None:
    with pytest.raises(RollbackError, match="no stable release"):
        RollbackManager().rollback_to_previous("v7", BlueGreenStrategy(), healthy)


def test_slugify_normalises_branch_names() -> None:
    assert slugify("feature/Add-Checkout Flow") == "feature-add-checkout-flow"
    assert slugify("///") == "preview"


def test_preview_environment_expiry_math() -> None:
    created = datetime.now(timezone.utc) - timedelta(hours=80)
    env = PreviewEnvironment(
        pr_number=42,
        branch="feature/x",
        stack_name="pr-42-feature-x",
        url="https://pr-42.preview.clouddeploy.dev",
        ttl_hours=72,
        created_at=created,
    )
    assert env.is_expired() is True


def test_preview_manager_creates_and_reaps(fake_provider: FakeProvider) -> None:
    manager = PreviewManager(provider=fake_provider, default_ttl_hours=72)
    env = manager.create_for_pr(101, "feat/login", template="static-site")

    assert env.url.endswith(".preview.clouddeploy.dev")
    assert len(env.resources) == 2
    assert all(spec.tags["preview"] == "true" for spec in (r.spec for r in env.resources))
    assert len(manager.list_active()) == 1

    reaped = manager.cleanup_expired(now=datetime.now(timezone.utc) + timedelta(hours=100))
    assert reaped == [101]
    assert manager.list_active() == []
