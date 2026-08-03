# Conflict Prevention Guide

## File Ownership

| Area | Primary owner | Notes |
| --- | --- | --- |
| `apps.orders` | Dat Sxinh | Coordinate payment status fields with Luan and Dat Tuat. |
| `apps.carts` | Dat Sxinh | Coordinate product stock reads with Linh and Lam. |
| `apps.payments` | Luan, Dat Tuat | Split gateway files by provider. Share base status model. |
| `apps.products` mutations | Linh | Coordinate model and serializer fields with Lam. |
| `apps.products` reads | Lam | Coordinate product DTO changes with Linh. |
| `src/app/checkout` | Dat Sxinh, Luan, Dat Tuat | Split pages by step. Avoid editing the same page in parallel. |
| `src/app/page.tsx`, `src/app/products` | Lam | Customer ProductListScreen entry point and alias. Coordinate shared product components with Linh. |
| `src/app/manager/products` | Linh | Lam may own read-only detail components if reused. |

## Before Starting a Task

1. Pull the latest main branch.
2. Read `docs/project-full-context.md` and the related design files.
3. Check whether another teammate is editing the same backend app or frontend
   route.
4. Write or update the API contract if frontend and backend are split across
   people.
5. Keep the PR scope to one business flow or one shared contract change.

## Shared Files That Need Extra Care

- `backend/apps/products/models.py`
- `backend/apps/products/serializers.py`
- `backend/apps/orders/models.py`
- `backend/apps/orders/serializers.py`
- `backend/apps/payments/models.py`
- `frontend/src/lib/apiClient.ts`
- `frontend/src/app/layout.tsx`
- `frontend/src/app/globals.css`
- shared checkout layout/order-progress components once created
- shared product card/detail popup components once created
- `frontend/package.json`
- `backend/requirements.txt`

Only edit these when necessary. Mention the reason in the PR description.

## API Contract Workflow

Before wiring frontend to backend, document:

- Endpoint path and HTTP method.
- Request JSON shape.
- Success response JSON shape.
- Error response shape.
- Auth or role requirements.
- Status values and transitions.

Use `docs/api/api-endpoints.md` or a feature-specific markdown file under
`docs/api/`.

## Merge Rules

- Do not merge with failing backend tests.
- Do not merge with failing frontend typecheck/build.
- Do not resolve conflicts by deleting another owner's code unless they approve.
- If a conflict involves a shared model or API response, discuss the contract
  first, then resolve code.
- If a conflict involves visual layout, compare with the approved mockup and
  screen specification first. The design document decides the target behavior.
