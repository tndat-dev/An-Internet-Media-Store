/**
 * Payment feature types and DTOs
 *
 * This file defines all TypeScript types for the payments feature to ensure
 * type safety and consistency across API calls, components, and state management.
 */

export type PaymentMethod = "VIETQR" | "PAYPAL";

export type PaymentStatusValue =
  | "PENDING"
  | "SUCCESS"
  | "FAILED"
  | "CANCELLED"
  | "REFUNDED";

/**
 * Request DTO for creating VietQR payment
 * Sent to POST /api/payments/vietqr/qr-code/
 */
export type CreateVietQRPaymentRequest = {
  order_id: string;
  amount: string;
};

/**
 * Response DTO from creating VietQR payment
 * Returned from POST /api/payments/vietqr/qr-code/
 */
export type VietQRPaymentResponse = {
  transaction_id: string;
  order_id: string;
  payment_method: PaymentMethod;
  status: PaymentStatusValue;
  amount: string;
  currency: string;
  transaction_reference: string;
  qr_payload: string;
  qr_image_url: string;
  qr_code?: string;
  qr_link?: string;
};

/**
 * Response DTO for payment status check
 * Returned from GET /api/payments/{transaction_id}/status/
 */
export type PaymentStatusResponse = {
  transaction_id: string;
  order_id: string;
  order_token?: string;
  order_status?: string;
  payment_method: PaymentMethod;
  status: PaymentStatusValue;
  amount: string;
  currency: string;
  transaction_reference: string;
};

/**
 * Request DTO for VietQR sandbox Test Callback
 * Sent to POST /api/payments/vietqr/test-callback/
 */
export type VietQRTestCallbackRequest = {
  transaction_id: string;
};

/**
 * Response DTO from VietQR sandbox Test Callback
 */
export type VietQRTestCallbackResponse = {
  status: "SUCCESS" | "FAILED";
  message: string;
};

/**
 * VietQR payment state for local UI management
 */
export type VietQRPaymentState =
  | "idle"
  | "creating"
  | "pending"
  | "checking"
  | "success"
  | "failed"
  | "error";

/**
 * Local component state for QR payment screen
 */
export type QRScreenState = {
  state: VietQRPaymentState;
  payment?: VietQRPaymentResponse;
  error?: string;
  lastCheckedAt?: string;
};

/**
 * Invoice/Order data passed to payment flow
 * Used to extract order_id and amount for QR generation
 */
export type InvoiceCheckoutData = {
  order_id: string;
  final_payable_amount: string;
  subtotal?: string;
  vat?: string;
  delivery_fee?: string;
};
