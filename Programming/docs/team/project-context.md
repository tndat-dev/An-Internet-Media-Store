# AIMS Project Context

## Purpose

AIMS is a full-stack e-commerce style application for ordering physical media
products. Coding work is split by core business capability, but each capability
must be implemented end to end across backend and frontend.

## Tech Stack

- Frontend: TypeScript, NextJS App Router, React.
- Backend: Python, Django, Django REST Framework.
- Database: PostgreSQL. Supabase is used as a managed PostgreSQL provider.
- Local database default: SQLite for quick backend skeleton checks unless
  `DATABASE_URL` is set.

## Current Coding 1 Baseline

- Backend has a runnable Django project in `Programming/backend`.
- Frontend has a runnable NextJS app in `Programming/frontend`.
- Existing backend business-rule tests cover product price validation, cart
  stock validation, delivery information, delivery fee, and order cancellation.
- The backend exposes `GET /api/health/`.
- The current frontend pages are only skeleton placeholders unless they have
  been rebuilt against the approved UI mockups and screen specifications.

## Design Source of Truth

- `docs/project-full-context.md` is the compact implementation guide.
- RequirementAnalysis, ArchitecturalDesign, DetailedDesign, and UnitTesting are
  source-of-truth folders. Code must follow them.
- UI work must follow `DetailedDesign/UserInterfaceDesign` screen specs,
  standardization rules, transition diagram, and mockups.
- Backend work must follow the SRS/use cases, data model, class design, and
  system interface design.
- If code conflicts with approved design documents, fix the code rather than
  weakening the design.

## Architectural Defaults

- Django owns business rules, persistence, and API contracts.
- NextJS owns pages, forms, UI state, and API consumption.
- Django migrations are the source of truth for schema changes.
- `DetailedDesign/DataModeling/aimsdb.sql` and `DatabaseDescription.docx` are
  approved data-model references. Django migrations should implement that model.
- API paths should live under `/api/`.

## Shared Success Criteria

Every core business increment should include:

- Backend endpoint or service logic.
- Frontend route, form, or view that exercises the business flow.
- Tests for backend business rules or API behavior.
- Clear API request and response shape documented before frontend integration.
- No unrelated refactors in the same pull request.
