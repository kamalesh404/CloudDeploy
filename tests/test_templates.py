"""Template rendering and variable-resolution tests."""

from __future__ import annotations

import pytest

from src.providers.base import ResourceKind
from src.templates import TEMPLATE_REGISTRY, available_templates, get_template
from src.templates.base import TemplateError, substitute


def test_registry_lists_builtin_templates() -> None:
    assert set(available_templates()) == {
        "api",
        "microservice",
        "static-site",
        "web-app",
        "worker",
    }


def test_web_app_renders_full_stack(web_app_specs) -> None:
    names = [spec.name for spec in web_app_specs]
    assert len(web_app_specs) == 5
    assert "shop-web" in names
    assert "shop-db" in names
    assert "shop-cdn" in names

    kinds = {spec.kind for spec in web_app_specs}
    assert kinds == {
        ResourceKind.NETWORK,
        ResourceKind.COMPUTE,
        ResourceKind.DATABASE,
        ResourceKind.STORAGE,
        ResourceKind.CDN,
    }


def test_missing_required_variable_raises() -> None:
    template = get_template("web-app")
    with pytest.raises(TemplateError, match="requires variable"):
        template.render({})


def test_defaults_and_choice_validation() -> None:
    template = get_template("web-app")
    specs = template.render({"app_name": "blog"})
    web = next(spec for spec in specs if spec.name == "blog-web")

    assert spec_tags_environment(specs) == "staging"
    assert web.replicas == 2
    assert web.size == "small"

    with pytest.raises(TemplateError, match="must be one of"):
        template.render({"app_name": "blog", "environment": "chaos"})


def spec_tags_environment(specs) -> str:  # noqa: ANN001 - helper local to tests
    network = specs[0]
    return network.tags["environment"] if "environment" in network.tags else _env_from_any(specs)


def _env_from_any(specs) -> str:  # noqa: ANN001 - helper local to tests
    for spec in specs:
        value = spec.tags.get("environment")
        if value:
            return str(value)
    raise AssertionError("no spec carries the environment tag")


def test_static_site_has_storage_and_cdn_only() -> None:
    specs = get_template("static-site").render({"site_name": "docs"})
    assert [spec.kind for spec in specs] == [ResourceKind.STORAGE, ResourceKind.CDN]
    cdn = specs[1]
    assert cdn.config["origin"] == "docs-site"


def test_worker_template_wires_queue_dependency() -> None:
    specs = get_template("worker").render({"worker_name": "images"})
    queue = next(spec for spec in specs if spec.kind is ResourceKind.QUEUE)
    pool = next(spec for spec in specs if spec.kind is ResourceKind.COMPUTE)

    assert f"{queue.name}" in pool.config["depends_on"]
    assert pool.config["autoscaling"]["metric"] == "queue_depth"


def test_microservice_attaches_to_mesh() -> None:
    specs = get_template("microservice").render({"service_name": "billing"})
    mesh = specs[0]
    service = specs[1]

    assert mesh.name == "clouddeploy-mesh"
    assert mesh.config["mtls"] == "strict"
    assert mesh.name in service.config["depends_on"]


def test_substitute_expands_known_variables() -> None:
    text = substitute("https://${app}.${domain}/health", {"app": "shop", "domain": "io"})
    assert text == "https://shop.io/health"


def test_describe_exposes_variables_for_cli() -> None:
    described = TEMPLATE_REGISTRY["api"].describe()
    variable_names = [variable["name"] for variable in described["variables"]]
    assert "api_name" in variable_names
