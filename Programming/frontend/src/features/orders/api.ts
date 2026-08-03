/*
 * SOLID Review
 * Principle: SRP
 * Reason: orders/api.ts groups draft order, delivery, invoice, mark-paid, tracking, cancellation, and preview endpoints in one module.
 * Impact: Place-order checkout APIs and post-payment/order-tracking APIs can change for different reasons but remain coupled in one file.
 * Improvement: Split checkout, public tracking, and payment-transition API clients into smaller modules.
 */

/*
 * Coupling/Cohesion: exposes order checkout use-case APIs only.
 * It depends on cart token headers for draft orders and keeps payment
 * and delivery submission separate from UI components.
 */
import { getCartToken } from "@/features/carts/api";
import { apiClient, parseApiError } from "@/lib/apiClient";

import type {
  DeliveryInfoPayload,
  DeliveryPreview,
  Invoice,
  ManagerOrder,
  Order,
  PaginatedOrders,
} from "./types";

// Re-exported for back-compat: components import parseApiError from this module.
export { parseApiError };

function cartHeaders() {
  return {
    "X-Cart-Token": getCartToken(),
  };
}

export function createDraftOrder() {
  return apiClient<Order>("/orders/draft/", {
    method: "POST",
    body: {},
    headers: cartHeaders(),
  });
}

export function submitDeliveryInfo(orderId: string, payload: DeliveryInfoPayload) {
  return apiClient<Order>(`/orders/${orderId}/delivery/`, {
    method: "POST",
    body: payload,
    headers: cartHeaders(),
  });
}

export function getInvoice(orderId: string) {
  return apiClient<Invoice>(`/orders/${orderId}/invoice/`);
}

export function confirmOrder(orderId: string) {
  return apiClient<Order>("/orders/", {
    method: "POST",
    body: { orderId },
  });
}

// Called after the payment gateway confirms success, to transition the order
// from PENDING_PAYMENT to PENDING_PROCESSING (see spec: order moves to
// processing once payment succeeds).
export function markOrderPaid(orderId: string) {
  return apiClient<Order>(`/orders/${orderId}/mark-paid/`, {
    method: "POST",
    body: {},
  });
}

// Live delivery-fee + totals preview for the delivery screen (no persistence).
export function previewDelivery(orderId: string, province: string, deliveryMethod: string) {
  return apiClient<DeliveryPreview>(`/orders/${orderId}/delivery/preview/`, {
    method: "POST",
    body: { province, deliveryMethod },
  });
}

// Public order lookup by view token (track order page).
export function getOrder(orderToken: string) {
  return apiClient<Order>(`/orders/${orderToken}/`);
}

// Cancel a paid order before approval, keyed by its cancel token.
export function cancelOrder(cancelToken: string) {
  return apiClient<Order>(`/orders/${cancelToken}/cancel/`, {
    method: "POST",
    body: {},
  });
}

// ---- Manager review queue (IsProductManager; token attached by apiClient) ----

export function listPendingOrders(page = 1) {
  const query = page > 1 ? `?page=${page}` : "";
  return apiClient<PaginatedOrders<ManagerOrder>>(`/orders/manage/pending/${query}`);
}

export function getManagerOrder(orderId: string) {
  return apiClient<ManagerOrder>(`/orders/manage/${orderId}/`);
}

export function approveOrder(orderId: string) {
  return apiClient<ManagerOrder>(`/orders/manage/${orderId}/approve/`, {
    method: "POST",
    body: {},
  });
}

export function rejectOrder(orderId: string, reason: string) {
  return apiClient<ManagerOrder>(`/orders/manage/${orderId}/reject/`, {
    method: "POST",
    body: { reason },
  });
}

// Cancelled/rejected VietQR orders needing (or having had) a manual refund.
export function listRefundingOrders(page = 1) {
  const query = page > 1 ? `?page=${page}` : "";
  return apiClient<PaginatedOrders<ManagerOrder>>(`/orders/manage/refunds/${query}`);
}

// Record that the manager has manually refunded a VietQR order.
export function markOrderRefunded(orderId: string, note?: string) {
  return apiClient<ManagerOrder>(`/orders/manage/${orderId}/mark-refunded/`, {
    method: "POST",
    body: { note: note ?? "" },
  });
}
