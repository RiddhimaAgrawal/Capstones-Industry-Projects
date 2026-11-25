# Capstones & Industry Projects

Backend Development track, two projects. Each folder has its own README with architecture, setup steps, test results and design notes.

| Folder | Project | Stack | Start here |
|---|---|---|---|
| [BE-01](BE-01) | **Digital Banking Core Platform**: accounts, atomic idempotent transfers, a double-entry ledger that always balances, KYC and fraud rules | Spring Boot 3.5 (Java 21), PostgreSQL 16, Flyway, Kafka, Keycloak, OpenAPI | [BE-01/README.md](BE-01/README.md) |
| [BE-03](BE-03) | **API Platform with Rate Limiting, Billing and Developer Portal**: an API sold as a product with keys, metering, plans and Stripe test billing | FastAPI, Redis, PostgreSQL, Celery, Stripe, OpenAPI Generator, Prometheus | [BE-03/README.md](BE-03/README.md) |

## Per-project deliverables

| Deliverable | BE-01 | BE-03 |
|---|---|---|
| Architecture diagram | [architecture.png](BE-01/docs/architecture.png), [ER diagram](BE-01/docs/er-diagram.png), [transfer sequence](BE-01/docs/transfer-sequence.png) | [architecture.png](BE-03/docs/architecture.png) |
| Documentation | [Setup guide](BE-01/docs/SETUP_GUIDE.md), [code walkthrough](BE-01/docs/CODE_WALKTHROUGH.md) | [EXPLANATION.md](BE-03/docs/EXPLANATION.md) |
| Test results | 32 integration tests (see README), [DB-level check](BE-01/verification/concurrency_check_output.txt) | [test_results.txt](BE-03/docs/test_results.txt) (24 passed) |
| Presentation | [Digital_Banking_Core.pptx](BE-01/presentation/Digital_Banking_Core.pptx) | [BE-03_Presentation.pptx](BE-03/docs/BE-03_Presentation.pptx) |
| Screenshots | `BE-01/docs/screenshots/` | `BE-03/docs/screenshots/` |
| Reflection | [BE-01/docs/REFLECTION.md](BE-01/docs/REFLECTION.md) | [BE-03/docs/REFLECTION.md](BE-03/docs/REFLECTION.md) |
| Demo video | add link | add link |

## Running either project

Prerequisites: Git, Docker Desktop or Podman. BE-01 also needs Java 21 and Maven; BE-03 needs Python 3.11+ for tests. Exact commands are in each project's README.
