# Full-Stack Workflow

Each owner is responsible for both backend and frontend for their core business.

## Recommended Order

1. Read `docs/project-full-context.md`.
2. Check the related use case, screen spec/mockup, data model, and class/system
   design.
3. Define or update the API contract.
4. Implement backend service, serializer, view, and tests.
5. Implement frontend feature API client.
6. Implement route/page/form or view component against the approved mockup.
7. Run backend tests and frontend checks.
8. Update docs if the contract or user flow changed.

## Backend to Frontend Handoff

Even when one person owns both sides, write the contract first. It prevents
breaking other flows that depend on shared models such as Product, Order, and
Payment.

Minimum contract details:

- Endpoint and method.
- Request JSON fields.
- Response JSON fields.
- Error format.
- Status enum values.
- Role requirement.
- Related screen(s) from the UI design.

## Suggested PR Shape

- One PR per core business slice.
- Include backend and frontend together when the feature is small.
- Split into API PR then UI PR only if the API contract is stable and reviewed.
- Avoid changing shared files in the same PR unless required by the feature.

## Local Checks Before PR

Backend:

```bash
cd Programming/backend
python manage.py check
pytest
```

Frontend:

```bash
cd Programming/frontend
npm run typecheck
npm run lint
npm run build
```

Design check:

- Compare the touched screen against the corresponding file in
  `DetailedDesign/UserInterfaceDesign/Mockups`.
- Confirm screen transition still follows
  `DetailedDesign/UserInterfaceDesign/ScreenTransitionDiagram.png`.
