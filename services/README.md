# AIMS independent services

The production-like lab deploys the following ten independently buildable
FastAPI artifacts. None imports the legacy Django application, each has its own
GHCR image and Kubernetes Rollout, and stateful domains own a PostgreSQL schema.
All service images are tested, scanned, signed and attested in one release batch.

| Service | Responsibility | State/integration |
|---|---|---|
| `api-gateway` | Single `/api` entry point and correlation IDs | HTTP routing to domain services |
| `auth-service` | Keycloak OIDC adapter | Keycloak; stores no password |
| `catalog-service` | Product source of truth | `catalog_service` schema |
| `cart-service` | Cart lifecycle and product snapshots | `cart_service` schema; Catalog HTTP API |
| `order-service` | Order aggregate and checkout | `order_service` schema; transactional outbox to Kafka |
| `payment-service` | Payment/VietQR state machine | `payment_service` schema; Kafka consumer/outbox |
| `inventory-service` | Stock and idempotent reservation | `inventory_service` schema; Kafka consumer/outbox |
| `notification-service` | Asynchronous notification worker | Kafka consumer; replace lab sink with SMTP/SMS provider |
| `search-recommendation-service` | Search facade and weighted recommendation | `search_recommendation_service` schema; Catalog HTTP API |
| `security-telemetry-service` | Audit ingestion and anomaly scoring | `security_telemetry_service` schema; Kafka + Isolation Forest |

`contracts/asyncapi/aims-events.yaml` versions the event-driven purchase slice:
`OrderCreated` → `InventoryReserved/Rejected` → `PaymentCompleted` →
notification. Database schema initialization uses per-service PostgreSQL
advisory locks so both replicas can start concurrently during an Argo Rollout.

This is deliberately a production-like teaching implementation rather than a
complete commerce product: all stateful services currently share one CNPG
database/credential while isolating schemas, Keycloak owns registration, the
search path falls back to Catalog until OpenSearch indexing is added, and the
notification provider is a lab sink. Those limitations do not couple service
images or deployment lifecycles back to Django.
