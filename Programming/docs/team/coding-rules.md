# Coding Rules

## General

- Read `docs/project-full-context.md` before coding any feature.
- Requirement and design documents are binding. Placeholder code is not.
- Keep each pull request focused on one core business increment.
- Do not mix formatting-only changes with feature changes.
- Do not rename shared files or routes without notifying the whole team.
- Do not create large placeholder file trees. Add files when they are needed by
  runnable code or tests.
- Prefer small, explicit functions over broad utility modules.
- Do not implement UI from imagination. Match the approved screen mockups,
  screen specs, and screen transition diagram.

## Backend Rules

- Follow the approved data model in `DetailedDesign/DataModeling`.
- Follow the class/system design concepts even though they are implemented with
  Django conventions: services, selectors, validators, gateways, and API
  boundary objects.
- Business rules belong in `services.py`, `validators.py`, or `selectors.py`.
- API request/response code belongs in `serializers.py` and `views.py`.
- Read-only query composition should go in `selectors.py` when it becomes more
  than a trivial ORM lookup.
- State-changing workflows should go in `services.py`.
- Validation that is independent from HTTP should go in `validators.py`.
- Keep Django models focused on data shape and simple invariants.
- Add or update tests whenever changing business rules.
- Do not call payment gateways directly from order views. Use payment services.
- Do not call external VietQR, PayPal, email, or Supabase production services in
  unit tests.
- Do not put frontend-specific naming into backend fields.

## Frontend Rules

- UI must follow `DetailedDesign/UserInterfaceDesign`:
  `ScreenStandardizationRequirements.docx`, `ScreenSpecifications.docx`,
  `ScreenTransitionDiagram.png`, and `Mockups/*.png`.
- Pages live under `src/app`.
- Feature API clients, hooks, and local types live under `src/features/<feature>`.
- Reusable layout or generic UI components live under `src/components`.
- Shared fetch logic lives in `src/lib/apiClient.ts`.
- Do not call `fetch` directly from many components. Wrap API calls in feature
  API modules first.
- Keep form validation aligned with backend validation, but backend remains the
  source of truth.
- Do not build manager/admin routes until the matching backend API exists or the
  PR explicitly includes both.
- Use the approved AIMS visual system: Roboto/Arial, primary `#0078D7`, accent
  `#FF6B35`, background `#F8F9FA`, white cards, 8px radius, 40px minimum button
  and input height.
- Preserve the approved customer flow:
  Product List -> Product Detail Popup -> Cart -> Delivery -> Invoice ->
  Payment Method -> QR/Card or PayPal Payment -> Order Result.
- Product detail is a popup/modal, not a standalone customer page unless the
  team updates the design.
- Do not show vague errors. Use field-level, actionable messages.

## API Rules

- All backend endpoints use `/api/<resource>/`.
- Use JSON request and response bodies.
- Use stable enum strings for statuses.
- Use ISO 8601 strings for datetimes.
- Use decimal values as strings when precision matters for money.
- Return field-level validation errors where possible.
- Keep response shapes documented in the PR or in `docs/api/` before frontend
  integration.
- API contracts must name the related screen(s) and business owner.
- Payment API errors must be mapped to safe user-facing messages; raw gateway
  exceptions must not be returned to the frontend.

## Test Rules

- Backend unit tests are required for pure business logic.
- Backend API tests are required when adding or changing endpoints.
- Frontend build and typecheck must pass before merging frontend changes.
- Add focused tests near the changed app. Avoid broad end-to-end tests for small
  business-rule changes in coding 1.
- Use equivalence partitioning, boundary value analysis, and decision tables for
  business rules called out in the Unit Test Plan.

## Definition of Done

- The related backend logic and frontend surface are both implemented.
- Existing tests pass.
- New or changed business logic has tests.
- API contract is clear enough for another teammate to consume.
- UI matches the relevant approved mockup/spec when a screen is touched.
- No unrelated files are changed.
