# API Endpoint Registry

Keep this file updated when adding or changing backend endpoints.

## Existing

| Method | Path | Owner | Purpose |
| --- | --- | --- | --- |
| GET | `/api/health/` | Shared | Backend health check. |
| POST | `/api/auth/login/` | Shared | User login (Customer/Manager/Admin). Verifies `password_hash`, updates `lastLogin`, returns `{token, user{roles}}`. |
| POST | `/api/auth/register/` | Shared | Public self-registration. Always creates a **CUSTOMER** account (role forced server-side); returns `{token, user}`. |
| POST | `/api/auth/logout/` | Shared | Revoke the caller's token. Requires `Authorization: Token <key>`. |
| GET | `/api/auth/me/` | Shared | Current authenticated user + roles. |
| POST | `/api/auth/change-password/` | Shared | Optional self-service password change; verifies old password, rotates token (returns new `{token}`). |
| GET/POST | `/api/admin/users/` | Admin | List internal users (filter `role`/`status`/`search`, paginated) / create a user (server-generated password emailed; never returned). Requires ADMIN. |
| GET/PATCH | `/api/admin/users/{id}/` | Admin | User detail / update profile (`fullName`,`phone`,`email`; email change notifies old+new). Requires ADMIN. |
| POST | `/api/admin/users/{id}/status/` | Admin | Set status `ACTIVE`/`DEACTIVATED`/`BLOCKED` (revokes tokens on block/deactivate). Requires ADMIN. |
| POST | `/api/admin/users/{id}/roles/` | Admin | Replace a user's roles (`roleNames[]`). Requires ADMIN. |
| POST | `/api/admin/users/{id}/reset-password/` | Admin | Reset to a new server-generated password (emailed; revokes tokens). Requires ADMIN. |
| GET/POST | `/api/admin/roles/` | Admin | List / create roles. Requires ADMIN. |
| GET | `/api/admin/audit-logs/` | Admin | List sensitive-action audit log (paginated). Requires ADMIN. |
| GET | `/api/products/` | Lam/Linh | List products for customer browsing and Product Manager workspace. Customer scope without filters returns 20 random products; filtered customer scope supports `search`, `category`, price range, and `sort`; manager scope supports `search` and `include_deleted=true`. |
| POST | `/api/products/` | Linh | Create one product with common fields and type-specific details. |
| GET | `/api/products/{id}/` | Lam/Linh | Get one product including type-specific details. |
| PATCH | `/api/products/{id}/` | Linh | Update product fields. Requires `stock_adjustment_reason` when stock quantity changes. |
| POST | `/api/products/delete/` | Linh | Delete/deactivate up to 10 products per request. Products with stock are deactivated; zero-stock products are marked deleted. |
| GET | `/api/products/histories/` | Linh | List latest product management history records. Supports optional `product_id`. |
| GET | `/api/cart/` | Dat Sxinh | Get anonymous server-side cart using `X-Cart-Token`. |
| POST | `/api/cart/items/` | Dat Sxinh | Add product quantity to cart after product availability and stock validation. |
| PATCH | `/api/cart/items/{id}/` | Dat Sxinh | Set cart item quantity after stock validation. |
| DELETE | `/api/cart/items/{id}/` | Dat Sxinh | Remove one cart item. |
| POST | `/api/orders/draft/` | Dat Sxinh | Create/update a pending-payment draft order from the current cart. |
| POST | `/api/orders/{id}/delivery/` | Dat Sxinh | Save delivery info, calculate delivery fee, and generate invoice. |
| GET | `/api/orders/{id}/invoice/` | Dat Sxinh | Get read-only invoice for checkout review. |
| POST | `/api/orders/` | Dat Sxinh | Confirm order for payment handoff while keeping status `PENDING_PAYMENT`. |
| POST | `/api/orders/{id}/mark-paid/` | Dat Sxinh | Fulfill a paid order: `PENDING_PAYMENT`->`PENDING_PROCESSING`, decrement stock (oversell-guarded), clear cart. Idempotent. Also called automatically by the payment-success seam. |
| POST | `/api/orders/{cancelToken}/cancel/` | Dat Sxinh | Customer cancels a paid order before approval; restores stock and issues a refund (PayPal auto / VietQR manual). Public, keyed by `cancel_token`. |
| GET | `/api/orders/{token}/` | Dat Sxinh | Public order lookup by order view token. |
| GET | `/api/orders/manage/pending/` | Dat Sxinh | Manager review queue (`PENDING_PROCESSING`). Requires PRODUCT_MANAGER token. |
| GET | `/api/orders/manage/{id}/` | Dat Sxinh | Manager order detail. Requires PRODUCT_MANAGER token. |
| POST | `/api/orders/manage/{id}/approve/` | Dat Sxinh | Approve order -> `APPROVED` (sets `processedBy`/`processedAt`). Requires PRODUCT_MANAGER token. |
| POST | `/api/orders/manage/{id}/reject/` | Dat Sxinh | Reject order -> `REJECTED`; restores stock and issues a refund. Requires PRODUCT_MANAGER token. |

## Planned by Core Business

| Business flow | Owner | Candidate endpoint | Status |
| --- | --- | --- | --- |
| View Product List | Lam | `GET /api/products/` | Implemented shared endpoint |
| View Product Detail | Lam | `GET /api/products/{id}/` | Implemented shared endpoint |
| CUD Product | Linh | `POST /api/products/` | Implemented |
| CUD Product | Linh | `PATCH /api/products/{id}/` | Implemented |
| CUD Product | Linh | `POST /api/products/delete/` | Implemented |
| Cart | Dat Sxinh | `GET /api/cart/` | Implemented |
| Cart | Dat Sxinh | `POST /api/cart/items/` | Implemented |
| Cart | Dat Sxinh | `PATCH /api/cart/items/{id}/` | Implemented |
| Cart | Dat Sxinh | `DELETE /api/cart/items/{id}/` | Implemented |
| Place Order | Dat Sxinh | `POST /api/orders/draft/` | Implemented |
| Place Order | Dat Sxinh | `POST /api/orders/{id}/delivery/` | Implemented |
| Place Order | Dat Sxinh | `GET /api/orders/{id}/invoice/` | Implemented |
| Place Order | Dat Sxinh | `POST /api/orders/` | Implemented |
| Place Order | Dat Sxinh | `POST /api/orders/{id}/mark-paid/` | Implemented (PENDING_PROCESSING transition after payment) |
| Place Order | Dat Sxinh | `GET /api/orders/{token}/` | Implemented |
| Pay Order by VietQR | Luan | `POST /api/payments/vietqr/qr-code/` | Implemented (mock gateway) |
| Pay Order by VietQR | Luan | `GET /api/payments/{transactionId}/status/` | Implemented |
| Pay Order by VietQR | Luan | `POST /api/payments/vietqr/callback/` | Implemented (mock callback) |
| Pay Order by PayPal | Dat Tuat | `POST /api/payments/paypal/initiate/` | Implemented |
| Pay Order by PayPal | Dat Tuat | `POST /api/payments/paypal/capture/` | Implemented |
| Pay Order by PayPal | Dat Tuat | `POST /api/payments/paypal/refund/` | Implemented |

Notes:

- VietQR uses a mock gateway (no real VietQR API call): `transaction_id` is the
  numeric PaymentTransaction id; `status` values are
  `PENDING`/`SUCCESS`/`FAILED`/`CANCELLED`/`REFUNDED` (native — no mapping).
  `payment_transactions` references `orders(order_id)` and refunds are persisted
  in `refund_transactions` (PayPal refund path).
- After a successful payment the order is fulfilled via `mark_order_paid`: status
  moves `PENDING_PAYMENT` -> `PENDING_PROCESSING`, stock is decremented (with an
  oversell guard), and the cart is cleared. This is idempotent and is now invoked
  automatically by the payment-success seam (VietQR callback and PayPal capture);
  the standalone `POST /api/orders/{id}/mark-paid/` remains for manual/demo use.
- Authentication: internal (Manager/Admin) endpoints use a custom token. Send
  `Authorization: Token <key>` obtained from `POST /api/auth/login/`. There is no
  global permission default — customer/public endpoints stay open (AllowAny);
  only manager/admin endpoints require a role (`PRODUCT_MANAGER`/`ADMIN`).
- Account model: customers never need an account (anonymous cart + order token);
  public `register` creates a CUSTOMER account only (future-friendly). Manager/Admin
  accounts are created by an Administrator (no public self-register for those) and
  receive a server-generated password by email. Passwords are always hashed and
  never returned; sensitive actions are recorded in the audit log and the affected
  user is emailed. Changing password is optional (not forced). Guards prevent an
  admin from blocking themselves, removing their own admin role, or removing the
  last active administrator.
- Order cancellation/rejection issues a refund per gateway: PayPal -> automatic
  (`RefundTransaction` PAYPAL_API/SUCCESS); VietQR -> manual
  (`RefundTransaction` MANUAL_BANK_TRANSFER/MANUAL_REQUIRED + manager email).
- Email uses Django's console backend by default (set `DJANGO_EMAIL_BACKEND` +
  `EMAIL_*` for real SMTP). Order confirmation/cancel/approve/reject and
  manual-refund notices are sent on commit and are non-fatal.
- Pagination: `GET /api/products/?scope=customer` returns a paginated payload
  `{count, next, previous, results}` (`page_size=20`, override via `page_size`,
  capped at 100) whenever a search/filter/sort is applied — "display all related
  products on each search page". With no filter it returns the fixed 20-random
  landing page in the same shape (`next`/`previous` null). `GET
  /api/orders/manage/pending/` is likewise paginated at 30 per page.
- Required type-specific fields (enforced by `ProductService` on create, and on
  update when the product type changes): Book — `authors, cover_type, publisher,
  publication_date`; Newspaper — `editor_in_chief, publisher, publication_date`;
  CD — `artists, record_label, tracklist, genre`; DVD — `disc_type, director,
  runtime_minutes, studio, language, subtitles`. Missing/blank required fields
  return `400` with messages under `type_details`.

## Rules

- Move an endpoint from planned to existing only after backend implementation
  and tests are merged.
- Add a request/response contract before frontend integration starts.
- Use `docs/team/api-contract-template.md` for new endpoint proposals.
- Include related screen(s), status values, and owner in every endpoint contract.
- Do not finalize payment endpoint names without checking the payment subsystem
  design in `docs/project-full-context.md`.
