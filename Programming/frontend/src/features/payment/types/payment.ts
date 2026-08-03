/**
 * Module: payment/types/payment.ts
 *
 * Coupling Level:
 * - Data Coupling with paymentApi.ts because API functions use these types
 *   as parameter/return types — only the necessary data structures are shared.
 * - Data Coupling with PayPalPaymentButton, PaymentResult components because
 *   they consume these types as props, receiving only the fields they need.
 *
 * Cohesion Level:
 * - Functional Cohesion because this file defines a single set of related
 *   data contracts for the payment domain.
 *
 * Reason:
 * Centralising payment types here ensures a single source of truth for the
 * payment data contract between frontend and backend. Changes to the API
 * response shape are reflected in one place only.
 */

// -----------------------------------------------------------------------
// Enums
// -----------------------------------------------------------------------

export type PaymentGateway = "PAYPAL" | "VIETQR";

export type PaymentStatus =
  | "PENDING"
  | "SUCCESS"
  | "FAILED"
  | "REFUNDED"
  | "CANCELLED";

// -----------------------------------------------------------------------
// Request DTOs (sent to backend)
// -----------------------------------------------------------------------

export interface InitiatePayPalPaymentRequest {
  order_id: string;
  amount?: number;
  currency?: string;
  return_url: string;
  cancel_url: string;
  description?: string;
}

export interface CapturePayPalPaymentRequest {
  provider_order_id: string;
  internal_order_id?: string;
}

export interface RefundPaymentRequest {
  order_id: string;
  capture_id: string;
  amount: number;
  currency: string;
  reason?: string;
}

// -----------------------------------------------------------------------
// Response DTOs (received from backend)
// -----------------------------------------------------------------------

export interface InitiatePayPalPaymentResponse {
  provider_order_id: string;
  orderID?: string;
  approval_url: string;
  transaction_id?: number;
  amount: string;
  currency: string;
  source_amount_vnd: string;
}

export interface CapturePayPalPaymentResponse {
  id?: number;
  order_id?: string;
  gateway?: "PAYPAL";
  provider_order_id?: string;
  capture_id?: string;
  amount?: string;
  currency?: string;
  status?: "SUCCESS" | "PENDING" | "FAILED" | "REFUNDED" | "CANCELLED";
  refund_id?: string;
  transaction_datetime?: string;
  transaction_id?: string;
  paypal_capture_id?: string;
  captured_amount?: number;
  captured_currency?: string;
  order_status?: string;
  order_total_vnd?: string;
  customer_name?: string;
  phone_number?: string;
  shipping_address?: string;
  delivery_province?: string;
}

export interface RefundPaymentResponse {
  refund_id: string;
  refunded_amount: number;
}

export interface PaymentTransaction {
  id: number;
  order_id: string;
  gateway: PaymentGateway;
  provider_order_id: string;
  capture_id: string;
  amount: number;
  currency: string;
  status: PaymentStatus;
  refund_id: string;
  transaction_datetime: string;
}
