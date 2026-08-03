/**
 * Checkout data storage helper
 *
 * Manages temporary storage of checkout data (invoice, cart, order) during
 * the multi-step checkout flow using browser sessionStorage.
 *
 * Note: sessionStorage is cleared when the browser tab closes, which is
 * appropriate for checkout flow. For persistent order tracking, use backend API.
 */

import type { InvoiceCheckoutData } from "@/features/payments/types";

const STORAGE_KEYS = {
  INVOICE: "aims.checkout.invoice",
  CART: "aims.checkout.cart",
  DELIVERY_INFO: "aims.checkout.delivery",
} as const;

// Order view token of the current order, persisted (localStorage) so the
// success page can link to /orders/[token] and show order details.
const ORDER_TOKEN_KEY = "aims.checkout.order-token";

export function saveOrderToken(token: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(ORDER_TOKEN_KEY, token);
  } catch {
    /* ignore */
  }
}

export function getOrderToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(ORDER_TOKEN_KEY);
  } catch {
    return null;
  }
}

/**
 * Save invoice/order data for payment flow
 *
 * @param data - Invoice/order data with order_id and final_payable_amount
 */
export function saveInvoiceData(data: InvoiceCheckoutData): void {
  try {
    sessionStorage.setItem(STORAGE_KEYS.INVOICE, JSON.stringify(data));
  } catch (error) {
    console.warn("Failed to save invoice data to sessionStorage:", error);
  }
}

/**
 * Retrieve saved invoice/order data
 *
 * @returns Invoice data or null if not found
 */
export function getInvoiceData(): InvoiceCheckoutData | null {
  try {
    const stored = sessionStorage.getItem(STORAGE_KEYS.INVOICE);
    return stored ? JSON.parse(stored) : null;
  } catch (error) {
    console.warn("Failed to parse invoice data from sessionStorage:", error);
    return null;
  }
}

/**
 * Clear invoice data after checkout is complete
 */
export function clearInvoiceData(): void {
  try {
    sessionStorage.removeItem(STORAGE_KEYS.INVOICE);
  } catch (error) {
    console.warn("Failed to clear invoice data:", error);
  }
}

/**
 * Clear all checkout data (invoice, cart, delivery)
 */
export function clearAllCheckoutData(): void {
  try {
    Object.values(STORAGE_KEYS).forEach((key) => {
      sessionStorage.removeItem(key);
    });
  } catch (error) {
    console.warn("Failed to clear checkout data:", error);
  }
}
