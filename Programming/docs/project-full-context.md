# AIMS Full Project Context

Read this file before coding. It is the compact source of truth for project
intent, business scope, frontend design, backend design, data model, and team
implementation rules.

## 1. Source-of-Truth Documents

Implementation must follow the design and requirement documents in this order:

1. Requirement analysis:
   - `AIMS-ProblemStatement-ver3.1.1.pdf` (the original problem brief at repo
     root; it is the only authoritative source for the shipping-fee figures used
     in section 9 — those numbers are not restated in the SRS/UC specs).
   - `RequirementAnalysis/SRS/Group18SoftwareRequirementSpecification-Ver1.2.docx`
   - `RequirementAnalysis/UCSpec/word/*.docx`
   - activity/use case diagrams exported as PNG.
2. Detailed design:
   - `DetailedDesign/UserInterfaceDesign/ScreenStandardizationRequirements.docx`
   - `DetailedDesign/UserInterfaceDesign/ScreenSpecifications.docx`
   - `DetailedDesign/UserInterfaceDesign/ScreenTransitionDiagram.png`
   - `DetailedDesign/UserInterfaceDesign/Mockups/*.png`
   - `DetailedDesign/DataModeling/DatabaseDescription.docx`
   - `DetailedDesign/DataModeling/aimsdb.sql`
   - class/system interface design DOCX and PNG exports.
3. Architectural design:
   - analysis class diagrams, communication diagrams, and sequence diagrams.
4. Programming docs:
   - these files explain how to translate the approved design into code.

If a placeholder implementation conflicts with the design documents, the design
documents win.

Notes:

- `.asta` files require Astah and are not readable directly in this workspace.
  Use the exported PNG files unless the team provides additional text.
- DOCX exports are readable and should be preferred over PDF when exact text is
  needed.

## 2. Project Scope

AIMS is an Internet Media Store for physical media products. The supported
product types are:

- Book
- CD
- DVD
- Newspaper

Actors:

- Customer: browses products, views detail, manages cart, places order, pays,
  views/cancels order before approval.
- Product Manager: manages products and stock, views product history, reviews
  pending orders, approves/rejects orders.
- Administrator: manages internal user accounts and roles.
- External systems: VietQR, PayPal Sandbox, email service.

Coding responsibilities currently focus on five full-stack core businesses:

| Owner | Core business | Main screens | Main backend area |
| --- | --- | --- | --- |
| Dat Sxinh | Place Order | Cart, Delivery, Invoice, Result integration | `orders`, `carts`, delivery/invoice services |
| Luan | Pay Order by VietQR | Payment Method, QR Payment, Result | `payments` VietQR gateway/service |
| Dat Tuat | Pay Order by PayPal | PayPal Payment, Result, refund path | `payments` PayPal gateway/service |
| Linh | CUD Product | Manager product create/update/delete | `products`, `product_histories` |
| Lam | View Product Detail | Product list, product detail popup | product read selectors/API |

## 3. Required Customer Flow

The customer flow must follow `ScreenTransitionDiagram.png`:

```text
ProductListScreen
  -> ProductDetailPopup
  -> CartScreen
  -> DeliveryInformationForm
  -> InvoiceScreen
  -> PaymentMethodScreen
  -> QRPaymentScreen or CardPaymentScreen
  -> OrderResultScreen
```

Back navigation must be available on process screens. Product detail is a popup
over the product list; when the popup is open, the parent screen is not
interactive.

## 4. Required Manager Flow

The manager flow must follow the screen transition design:

```text
ManagerLogin
  -> ManagerDashboard
  -> ManagerProductList
  -> CreateProductScreen
  -> UpdateProductScreen
  -> DeleteProductScreen
```

The manager also has order-management screens for pending orders, order detail,
approval, and rejection. Build these only when the related backend contracts are
being implemented.

## 5. Frontend Design Rules

### Layout

- Minimum desktop target: `1366 x 768`.
- Design width: `1440px`.
- Desktop breakpoint: `>= 1200px`.
- Mobile breakpoint: `< 768px`.
- Header:
  - AIMS logo on the left.
  - Main screen title centered where the mockup/spec requires it.
  - Utility actions on the right, such as cart, account, search, filter, sort,
    logout, or manager navigation.
- Main content uses light gray application background and white surfaces/cards.
- Product grids adapt from 4 columns to 2 columns to 1 column.
- Delivery and payment layouts stack vertically on smaller screens.
- Primary process actions must remain visible and accessible.

### Visual System

- Font: Roboto first, then Arial/sans-serif fallback.
- Main title: 24px bold.
- Section title: 20px semibold.
- Card/popup title: 18px semibold.
- Body: 16px regular.
- Secondary text: 14px regular.
- Helper text: 12px regular.

Colors:

- Primary: `#0078D7`
- Accent: `#FF6B35`
- Success: `#2E7D32`
- Warning: `#ED6C02`
- Error: `#D32F2F`
- Background: `#F8F9FA`
- Surface/card: `#FFFFFF`
- Primary text: `#212121`
- Secondary text: `#616161`
- Border/divider: `#D9D9D9`

Button rules:

- Primary button: primary background, white text, 8px radius, min height 40px.
- Secondary button: white background, primary border/text.
- Danger button: red background, white text.
- Disabled button: light gray background, gray text, non-clickable.
- Destructive actions require confirmation.

Input rules:

- Standard height: 40px.
- Border radius: 8px.
- Default border: neutral border.
- Focus border: primary.
- Error border: error color plus helper text directly below the field.
- Labels must remain visible; do not rely only on placeholders.

Icons:

- Design says Material Icons. In the current React codebase, use one icon
  library consistently if installed later, but keep icon meaning aligned with
  Material icon names in the design: search, shopping_cart, arrow_back, close,
  filter_list, sort, delete, edit, check_circle, error, info.
- Important action icons should have text labels.

### Data Formatting

- Currency: `1,000 VND` consistently within a screen.
- Numeric values use thousands separators.
- Zero currency displays as `0 VND`.
- Date: `DD/MM/YYYY`.
- Time: `HH:mm`.
- Datetime: `DD/MM/YYYY HH:mm`.
- Product cards truncate long titles to 2 lines with ellipsis.
- Full title must be visible in product detail.
- Do not render raw HTML/scripts from user input.

### Validation UX

Validation order:

1. Required/empty check.
2. Format check.
3. Business rule check.

Validation display:

- Field-level errors appear below the related field.
- Invalid fields use red border.
- Form-wide errors also appear as a top banner.
- User-entered data must not be cleared after validation fails.
- Errors must be clear and actionable. Do not show vague messages like
  `Error occurred`, `Invalid input`, or raw gateway exceptions.

## 6. Screen Requirements

### Product List Screen

This is the customer homepage and software entry screen. When the software
starts, it must show 20 random customer-visible products before the customer
applies search, filter, or sort controls.

Must provide:

- Search by title or category.
- Category filter.
- Price range filter.
- Sort dropdown.
- Product cards with image, type/category, title, current price, stock status,
  Add to Cart, and detail action.
- Pagination or load-more behavior.
- Cart entry point.

Fields:

- Product title max 80 characters in card view, max 2 lines.
- Category max 30 characters.
- Price shown as `1,000 VND`.
- Stock status uses text and icon, not color alone.

### Product Detail Popup

Must provide:

- Modal/popup over parent product list.
- Close button in top-right.
- Product image, title, type/category, price, description.
- Type-specific attributes.
- Quantity selector.
- Add to Cart button.
- Not found/unavailable states.

### Cart Screen

Must provide:

- List of cart items.
- Quantity update.
- Remove item action with confirmation.
- Item subtotal and cart subtotal excluding VAT.
- Insufficient-stock warning showing available quantity.
- Continue Shopping and Place Order actions.

### Delivery Information Form

Must provide:

- Recipient name.
- Phone number.
- Email.
- Province/city.
- Detailed address.
- Optional delivery instructions when supported.
- Delivery method selection.
- Auto-updated delivery fee and order summary.
- Back to Cart and Continue to Invoice actions.

Phone number frontend rule follows the UI spec: 10-11 digits numeric for direct
input display. Backend may also support separators if required by use-case
text; keep API validation contract explicit.

### Invoice Screen

Must display read-only:

- Customer and delivery information.
- Product list with title, unit price, quantity, item total.
- Subtotal excluding VAT.
- VAT amount at 10%.
- Total including VAT.
- Delivery fee.
- Final payable amount emphasized.
- Back and Proceed to Payment actions.

Shipping fee is not subject to VAT.

### Payment Method Screen

Must provide:

- QR Code Payment option.
- Card / PayPal payment option.
- Order ID.
- Final payable amount.
- Back and Continue actions.
- Selected method visibly highlighted.

### QR Payment Screen

Must provide:

- Centered QR code.
- Amount.
- Order ID.
- Transaction content/reference.
- Payment status: Waiting, Paid, Timeout, or Failed.
- Buttons: Back, Switch Payment Method, Check Payment Status.
- Loading/busy state while checking payment status.

### Card / PayPal Payment Screen

Must provide:

- PayPal-hosted checkout entry point for card or PayPal wallet payment.
- Order ID and VND invoice total.
- Clear notice that the PayPal charge amount is calculated by the backend from
  the saved invoice.
- CVV.
- Billing email.
- Payment summary.
- Back, Switch Payment Method, Pay Now actions.
- Secure transaction note.

### Order Result Screen

Must provide:

- Payment result.
- Order status. After success, show `Pending Processing`.
- Customer name, phone, shipping address, province/city.
- Total amount paid.
- Transaction ID, content, datetime.
- View Order Information and Back to Home actions.

### Product Manager Create/Update/Delete Screens

Create product must include:

- General product fields: title, category, price/current price, barcode,
  description, weight, dimensions, stock quantity, product type, image.
- Dynamic type-specific fields for Book, CD, DVD, Newspaper.
- Validation messages, reset, cancel/back, create action.

Update product must include:

- Current product information loaded into the form.
- Editable common fields and type-specific fields.
- Product ID read-only.
- Reset original data, cancel/back, update action.

Delete product must include:

- Confirmation dialog.
- Selected product summary.
- Warning message.
- Cancel and Confirm Delete.
- Danger visual treatment.

## 7. Backend Architecture Rules

Backend implementation uses Django/DRF, but must preserve the design concepts:

- Entities map to Django models.
- Controllers map to DRF views/viewsets or thin orchestration entrypoints.
- Services contain business workflows and state changes.
- Selectors contain read/query composition.
- Validators contain reusable validation rules.
- Gateways/boundaries contain external API communication.
- Subsystem facades expose payment integrations to the rest of the app.

Never put core business logic directly in React components or DRF views.

Recommended Django app boundaries:

- `apps.products`: product models, product subtype models, product read/write
  APIs, price validation, status/deletion rules.
- `apps.product_histories`: product history records and history services, or a
  submodule under `products` if the team keeps it small.
- `apps.carts`: cart item quantity and stock validation.
- `apps.orders`: order placement, delivery info, invoice generation, status
  transitions, customer order lookup/cancellation.
- `apps.payments`: shared payment transaction model/services and provider
  integrations.
- `apps.payments.gateways.vietqr`: VietQR gateway/API boundary.
- `apps.payments.gateways.paypal`: PayPal gateway/API boundary.
- `apps.users`: internal users, roles, authentication/authorization when needed.

## 8. Database Model

The approved data model uses PostgreSQL and includes:

- `carts`, `cart_items`
- `users`, `roles`, `user_roles`
- `products`
- subtype tables: `books`, `cds`, `dvds`, `newspapers`
- `product_histories`
- `orders` (links to a cart via nullable `cart_id` for the draft-order flow)
- `order_items`
- `delivery_infos`
- `invoices`
- `payment_transactions`
- `refund_transactions`

Key enums:

- `user_status_enum`: `ACTIVE`, `DEACTIVATED`, `BLOCKED`
- `product_type_enum`: `BOOK`, `CD`, `DVD`, `NEWSPAPER`
- `product_status_enum`: `ACTIVE`, `DEACTIVATED`, `DELETED`
- `history_action_type_enum`: `CREATE`, `UPDATE`, `DELETE`, `DEACTIVATE`,
  `STOCK_ADJUST`
- `order_status_enum`: `PENDING_PAYMENT`, `PENDING_PROCESSING`, `APPROVED`,
  `REJECTED`, `CANCELLED`
- `payment_status_enum`: `PENDING`, `SUCCESS`, `FAILED`, `CANCELLED`,
  `REFUNDED`
- `payment_method_enum`: `QR_CODE`, `CREDIT_CARD`
- `refund_status_enum`: `PENDING`, `SUCCESS`, `FAILED`, `MANUAL_REQUIRED`
- `refund_method_enum`: `PAYPAL_API`, `MANUAL_BANK_TRANSFER`

Cart status is a plain string field (`OPEN`, `CHECKED_OUT`), not a PostgreSQL
enum type.

The reconciled SQL (`aimsdb.sql`) and the Django implementation differ from the
older `DatabaseDescription`/ERD PNG exports in ways the code follows; the SQL is
authoritative and those images are pending regeneration:

- `payment_transactions` references `orders(order_id)` (not `invoices`) and is
  gateway-agnostic: a `gateway` field with values `PAYPAL` and `VIETQR`
  identifies the provider. `payment_method_enum` is still defined in the schema
  but is unused by the implementation — discriminate by `gateway`, not
  `payment_method`.
- `carts`, `cart_items`, and `orders.cart_id` exist in the SQL and
  implementation but are absent from the older ERD/`DatabaseDescription` exports.

Important constraints:

- Product barcode is unique.
- Product dimensions and weight are non-negative.
- Original value and current price are non-negative.
- Current price must be between 30% and 150% of original value.
- Stock quantity is non-negative.
- Product can be `DELETED` only when stock is zero.
- Order view and cancellation use unique tokens.
- Order item stores product title and price snapshots.
- Invoice total formula:
  `total_product_price_incl_vat = total_product_price_excl_vat + vat_amount`
- Final payable formula:
  `total_amount_to_pay = total_product_price_incl_vat + delivery_fee`
- Manual bank transfer refunds require a manual note.

Django migrations should implement this model. The SQL file is design reference
and Supabase/PostgreSQL export reference, not a replacement for migrations.

## 9. Core Business Rules

### Product

- Product types: Book, CD, DVD, Newspaper.
- Product price excludes 10% VAT at storage/input time.
- Current price must be within `[30%, 150%]` of original value.
- Product status controls sale availability.
- Deleting more than 10 products per request is not allowed.
- Deleting more than 20 products per day per manager is not allowed.
- If selected product stock is zero, it can be deleted/marked deleted.
- If selected product stock is greater than zero, it must be deactivated instead
  of physically deleted.
- Create/update/delete/deactivate/stock adjustment actions must be logged in
  product history.

### Cart

- Quantity must be greater than 0.
- Requested quantity must not exceed available stock.
- Cart subtotal is product price excluding VAT.
- Stock must be checked before place order can continue.

### Delivery

- Required: receiver name, phone, province/city, detailed address, email.
- Shipping fee rule:
  - Hanoi / Ho Chi Minh City: `22,000 VND` for first `3kg`.
  - Other provinces: `30,000 VND` for first `0.5kg`.
  - Extra fee: `2,500 VND` per additional `0.5kg` or part thereof.
  - If total item value excluding VAT is greater than `100,000 VND`, reduce
    delivery fee by up to `25,000 VND`.
- Delivery fee is not subject to VAT.
- Changing address or delivery method recalculates invoice/fee.

### Invoice

- Product VAT is 10%.
- Store and display:
  - subtotal excluding VAT
  - VAT amount
  - total including VAT
  - delivery fee
  - final payable amount

### Orders

- After successful payment, order status becomes `PENDING_PROCESSING`.
- Customer can cancel only before approval.
- Customer receives invoice and transaction information by email.
- Stock quantity is updated after successful paid order.

### VietQR Payment

- Default payment method.
- AIMS generates a QR code using VietQR credentials.
- QR screen displays QR image, amount, order ID, transaction reference/content.
- Payment status can be checked manually or by callback/polling.
- Callback must verify status and amount before recording success.
- VietQR does not support automated refund; cancellation/rejection after success
  requires manual refund handling.

### PayPal Payment

- Alternative payment method.
- PayPal flow creates an order, captures payment after buyer approval, and
  records the payment transaction.
- Successful payment clears cart and moves order to `PENDING_PROCESSING`.
- If a paid PayPal order is cancelled before approval, refund is automatic
  through PayPal API.

## 10. Payment Subsystem Design

Both payment methods must be hidden behind service/gateway abstractions. The
rest of the system should not know HTTP details of VietQR or PayPal.

VietQR design concepts:

- `IPaymentQRCode`
- `VietQRSubsystem`
- `VietQRController`
- `VietQRGateway`
- `VietQRServiceAPI`
- `VietQRCallbackHandler`
- `QRCode`, `VietQRRequest`, `VietQRResponse`, `TokenResponse`

PayPal design concepts:

- `IPaymentCreditCard`
- `IRefundGateway`
- `PayPalSubsystem`
- `PayPalController`
- `PayPalGateway`
- `PayPalServiceAPI` or boundary
- `CreditCard`
- `PayPalOrderRequest`, `PayPalOrderResponse`, `PayPalCaptureResponse`
- `PayPalRefundRequest`, `PayPalRefundResponse`, `PayPalTokenResponse`

Shared payment concepts:

- `PaymentTransaction`
- `RefundTransaction`
- `PaymentException`
- `PaymentTimeoutException`
- `PaymentDeclinedException`
- `InsufficientBalanceException`
- `InvalidTransactionException` where applicable.

Note on design sources: the System Interface Design and the General Class Diagram
use two different name sets for the same payment subsystems (for example
`IPaymentQRCode`/`IPaymentCreditCard` versus `IQRPaymentGateway`/`IPaymentGateway`,
and `QRCode` versus `QRData`). This file follows the System Interface Design
names. For transaction status, follow the database `payment_status_enum` value
`SUCCESS`; the class diagram's `PaymentStatus.COMPLETED` is superseded by the
reconciled data model and the implementation.

## 11. API Contract Rules

Before coding frontend against backend, document the endpoint in
`docs/api/api-endpoints.md` or a feature contract file.

Minimum contract:

- Endpoint path and method.
- Owner.
- Request JSON.
- Success response JSON.
- Error response JSON.
- Status enum values.
- Auth/role requirement.
- Related screen(s).

Default API shape:

- Backend endpoint prefix: `/api/`.
- JSON only.
- Frontend-facing response fields should be consistent; if the team chooses
  camelCase for frontend API, serializers must convert explicitly.
- Money values should be decimal strings or integer VND values consistently per
  endpoint. Do not mix in one response.
- Status values must match design/database enums.

## 12. Testing Rules

Unit testing scope follows the Unit Test Plan:

- Product price validation.
- Delivery fee calculation.
- Cart quantity/stock validation.
- Delivery information validation.
- Order cancellation/refund eligibility.

Backend:

- Use `pytest` and `pytest-django`.
- Keep business rules testable in validators/services.
- Mock external services such as PayPal, VietQR, email, and production
  Supabase.
- Use equivalence partitioning, boundary value analysis, and decision tables for
  business rules.

Frontend:

- At minimum, typecheck, lint, and build must pass.
- Add Vitest/Jest/React Testing Library tests when frontend has isolated
  validation, formatting, or state logic.
- Visual/layout correctness is checked against mockups and screen specs.

## 13. Implementation Checklist

For every feature PR:

- Requirement/use case checked.
- Screen spec/mockup checked if UI is touched.
- Data model/class design checked if backend is touched.
- API contract written or updated.
- Backend logic placed in services/selectors/validators, not views.
- Frontend calls API through feature API modules, not random fetch calls.
- Errors are field-level and user-readable.
- Status and enum values match approved design.
- Existing tests pass.
- New business rules have tests.
- No unrelated refactor or placeholder tree expansion.
