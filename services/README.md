# AIMS service extraction

The current Django application is a modular monolith. This directory is the
target boundary for independently buildable services; a service is not declared
extracted until it has its own image, database credential/schema, API/event
contract, migration history and integration tests.

`notification-service` and `inventory-service` are the first independent
artifacts. Inventory owns schema `inventory_service`, consumes `OrderCreated`
idempotently and publishes its result through a transactional outbox.

Remaining extraction order: order → payment → catalog → search-recommendation
→ cart → auth → gateway → security-telemetry. `contracts/asyncapi/aims-events.yaml`
is the compatibility contract for the event-driven purchase slice.
