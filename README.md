# CloudDeploy

![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)
![Version](https://img.shields.io/badge/version-1.4.0-green.svg)
![License](https://img.shields.io/badge/license-MIT-lightgrey.svg)
![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)
![Code style](https://img.shields.io/badge/code%20style-ruff-000000.svg)

**Ship cloud applications in minutes, not days.**

CloudDeploy is a multi-cloud deployment platform that turns a single declarative
YAML file into fully provisioned infrastructure across AWS, Google Cloud,
Azure, and DigitalOcean. Pick a battle-tested template, plan your changes,
and roll out with confidence using progressive delivery strategies.

## Features

- **Multi-cloud providers** — First-class support for AWS, GCP, Azure, and
  DigitalOcean behind a single provider abstraction.
- **Deployment templates** — Production-grade blueprints for web apps, APIs,
  static sites, background workers, and microservices.
- **Infrastructure-as-code** — Declarative YAML DSL with compilation,
  validation, dependency resolution, and cycle detection.
- **Plan & apply workflow** — Terraform-style diffs show exactly what will be
  created, updated, or destroyed before anything touches the cloud.
- **Remote state** — Pluggable state backends with local and S3-compatible
  storage out of the box.
- **Progressive delivery** — Rolling, blue-green, and canary deployment
  strategies with automated health gates and instant rollback.
- **Preview environments** — Ephemeral per-pull-request stacks with automatic
  TTL cleanup.
- **Built-in observability** — Metrics collection, log aggregation, alert
  rules with escalation, and uptime monitoring.
- **Managed SSL & DNS** — Automated Let's Encrypt certificates with renewal,
  plus DNS record management for Cloudflare, Route53, and DigitalOcean.

## Architecture

```
                        ┌──────────────────────────────────┐
   clouddeploy.yaml     │           CloudDeploy CLI        │
  ─────────────────────►│  init · deploy · plan · monitor  │
                        └────────────────┬─────────────────┘
                                         │  provider interface
              ┌──────────────┬───────────┴────────┬───────────────┐
              ▼              ▼                    ▼               ▼
            AWS             GCP                Azure        DigitalOcean
        EC2/ECS/Lambda   GCE/Cloud Run      VMs/App Service   Droplets/Apps
        S3/RDS/CloudFront Cloud SQL/GCS     SQL/Blob         Spaces/DBs
```

The compiler converts YAML + a template into a list of typed
`ResourceSpec` objects. The validator checks naming rules and resolves
`depends_on` edges into a topological order. The planner diffs desired
state against the configured state backend, and the provider layer
translates specs into real cloud resources.

## Quickstart

```bash
pip install clouddeploy

clouddeploy init --template web-app --provider aws
clouddeploy plan      # preview the infrastructure changes
clouddeploy apply     # provision the stack
clouddeploy deploy --image registry.example.com/shop:1.2.0
clouddeploy status
```

Example `clouddeploy.yaml`:

```yaml
name: shop
provider: aws
region: us-east-1
template: web-app
variables:
  app_name: shop
  domain: shop.example.com
  environment: production
  replicas: 4
```

## CLI Reference

| Command                     | Description                                  |
| --------------------------- | -------------------------------------------- |
| `clouddeploy init`          | Scaffold a new project from a template       |
| `clouddeploy plan`          | Compute and display an execution plan        |
| `clouddeploy apply`         | Create or update infrastructure              |
| `clouddeploy diff`          | Show drift between state and configuration   |
| `clouddeploy deploy`        | Release a new application version            |
| `clouddeploy destroy`       | Tear down a stack                            |
| `clouddeploy status`        | List provisioned resources                   |
| `clouddeploy logs`          | Search and stream aggregated logs            |
| `clouddeploy metrics`       | Show dashboard summaries                     |
| `clouddeploy alerts`        | Evaluate and list alert rules                |

## Project Layout

```
src/
  providers/    Cloud provider abstractions and implementations
  templates/    Reusable deployment blueprints
  infra/        DSL compiler, validator, planner, state backends
  monitoring/   Metrics, logs, alerts, health checks
  deploy/       Deployment strategies, rollback, previews
  ssl/          Certificate issuance and validation
  dns/          DNS record management across providers
cli/            Click-based command line interface
tests/          Pytest suite
docs/           User guides and API reference
```

## Development

```bash
git clone https://github.com/clouddeploy/clouddeploy.git
cd clouddeploy
make install
make test
make lint
```

## License

MIT — see [LICENSE](LICENSE) for details.
