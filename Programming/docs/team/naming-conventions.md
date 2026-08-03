# Naming Conventions

## Repository

- Directories use kebab-case in frontend routes when they are URL segments.
- Python packages use snake_case.
- Django apps use plural nouns: `products`, `orders`, `carts`, `payments`.
- Documentation files use kebab-case.

## Backend

### Files

- `models.py`: database models.
- `serializers.py`: DRF serializers.
- `views.py`: DRF views or viewsets.
- `urls.py`: app URL routes.
- `services.py`: write workflows and business actions.
- `selectors.py`: read/query workflows.
- `validators.py`: reusable validation rules.
- `tests/test_<business_rule>.py`: focused tests.

### Python Names

- Functions and variables: `snake_case`.
- Classes: `PascalCase`.
- Constants: `UPPER_SNAKE_CASE`.
- Enum values: stable uppercase strings, for example `PENDING_PROCESSING`.
- Test names: `test_<expected_behavior>`.

### API Names

- URL resources: plural nouns, for example `/api/products/`.
- Path params: use `id` for internal IDs and `token` for public order lookup.
- JSON fields: `camelCase` for frontend-facing API responses.
- Internal Python fields: `snake_case`.

If serializers convert between `snake_case` and `camelCase`, keep the conversion
explicit and consistent.

## Frontend

### Files and Components

- Route files: `page.tsx`, `layout.tsx`, `loading.tsx`, `error.tsx`.
- React components: `PascalCase.tsx`.
- Feature API files: `api.ts`.
- Feature hooks: `hooks.ts`.
- Feature types: `types.ts`.
- Utility files: `camelCase.ts`.

### TypeScript Names

- Components: `PascalCase`.
- Functions and variables: `camelCase`.
- Types and interfaces: `PascalCase`.
- Constants: `UPPER_SNAKE_CASE`.
- Boolean variables: prefix with `is`, `has`, `can`, or `should`.

### Routes

- Customer product list / homepage: `/`.
- Customer product list alias: `/products` redirects to `/` for older links.
- Customer product detail: open `ProductDetailPopup` from `/` according
  to the approved screen transition. Do not create a standalone customer detail
  page unless the team updates the UI design.
- Cart: `/cart`.
- Delivery checkout: `/checkout/delivery`.
- Invoice checkout: `/checkout/invoice`.
- Payment checkout: `/checkout/payment`.
- QR payment: `/checkout/payment/qr`.
- Card payment: `/checkout/payment/card`.
- Checkout success: `/checkout/success`.
- Public order lookup: `/orders/[token]`.
- Product manager product list: `/manager/products`.
- Product manager product create: `/manager/products/create`.
- Product manager product edit: `/manager/products/[id]/edit`.
- Product manager delete should be a confirmation modal/dialog over the manager
  product list, not a standalone route unless design changes.

### Screen Names

When naming UI components, use the approved screen names where possible:

- `ProductListScreen`
- `ProductDetailPopup`
- `CartScreen`
- `DeliveryInformationForm`
- `InvoiceScreen`
- `PaymentMethodScreen`
- `QRPaymentScreen`
- `CardPaymentScreen`
- `OrderResultScreen`
- `CreateProductScreen`
- `UpdateProductScreen`
- `DeleteProductDialog`

## Branches and Commits

- Branch format: `<owner>/<business>-<short-task>`.
- Examples:
  - `dat-sxinh/place-order-api`
  - `luan/vietqr-payment-ui`
  - `dat-tuat/paypal-capture`
  - `linh/product-create-form`
  - `lam/product-detail-page`
- Commit messages should start with the area:
  - `backend: add order placement service`
  - `frontend: add product detail route`
  - `docs: add API contract notes`
