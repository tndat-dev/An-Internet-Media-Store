/**
 * Shared application constants.
 * Single source of truth for business rules and magic values that were
 * previously hardcoded across components. Keep these aligned with the backend
 * (see apps/products validators/services and the project full-context spec)
 */

// Supported product types (must match backend ProductType enum).
export const PRODUCT_TYPES = ["Book", "CD", "DVD", "Newspaper"] as const;
export type ProductTypeLabel = (typeof PRODUCT_TYPES)[number];

// Product current price must stay within [30%, 150%] of its original value.
export const PRICE_RATIO_MIN = 0.3;
export const PRICE_RATIO_MAX = 1.5;

// Stock at or below this count is surfaced as "low stock" in the manager UI.
export const LOW_STOCK_THRESHOLD = 3;

// Product deletion limits (must match backend ProductService).
export const MAX_DELETE_PER_REQUEST = 10;

// Product VAT rate applied to product prices (delivery fee is VAT-exempt).
export const VAT_RATE = 0.1;

// sessionStorage/localStorage keys used across the checkout flow.
export const ORDER_ID_STORAGE_KEY = "aims-current-order-id";
