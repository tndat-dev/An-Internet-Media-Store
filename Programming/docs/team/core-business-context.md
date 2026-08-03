# Core Business Context

## Ownership

| Owner | Core business | Primary user | Backend area | Frontend area |
| --- | --- | --- | --- | --- |
| Dat Sxinh | Place Order | Customer | `apps.orders`, `apps.carts` | `src/app/checkout`, `src/features/orders`, `src/features/cart` |
| Luan | Pay Order by VietQR | Customer | `apps.payments` later, `apps.orders` integration | `src/app/checkout/payment`, `src/features/payments` |
| Dat Tuat | Pay Order by PayPal | Customer | `apps.payments` later, PayPal gateway | `src/app/checkout/payment`, `src/features/payments` |
| Linh | CUD Product | Product Manager | `apps.products` | `src/app/manager/products`, `src/features/products` |
| Lam | View Product Detail | Customer, Product Manager | `apps.products` selectors/API | `src/app/page.tsx`, `ProductDetailPopup`, manager product detail |

## Boundaries

### Place Order

- Owns delivery information validation, delivery fee application, cart-to-order
  conversion, order token creation, and customer order confirmation flow.
- Must not implement payment gateway details.
- Can depend on product availability and cart validation.

### Pay Order by VietQR

- Owns VietQR payment initiation, manual confirmation state, and payment result
  display for orders.
- Must not duplicate PayPal gateway logic.
- Must integrate with order payment status using a shared payment interface.

### Pay Order by PayPal

- Owns PayPal payment creation, approval handling, cancellation handling, and
  refund behavior where required.
- Must not duplicate VietQR-specific logic.
- Must integrate through the same payment status model used by VietQR.

### CUD Product

- Owns create, update, and delete product behavior for Product Manager.
- Owns product price validation integration and manager-side product forms.
- Must coordinate schema changes with View Product Detail to avoid product model
  conflicts.

### View Product Detail

- Owns customer and manager product detail reads.
- Owns product detail API response contract and display of product metadata.
- Must not include manager-only mutation behavior.

## Shared Concepts

- `Product`: sellable item with price, original value, stock, and display data.
- `Cart`: customer-selected products and quantities before order creation.
- `Order`: committed customer purchase request.
- `Payment`: payment attempt or result tied to an order.
- `DeliveryInfo`: customer name, phone, address, and delivery fee context.

## Integration Rules

- If two owners need the same model field, agree on the field name and type
  before either PR changes it.
- If two owners need the same frontend route, split by component ownership, not
  by competing page implementations.
- Payment owners must share one payment status vocabulary.
- Product owners must share one product response DTO for customer-facing product
  data.
