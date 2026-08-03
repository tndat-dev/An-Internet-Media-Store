/*
 * SOLID Review
 * Principle: SRP
 * Reason: payments/api.ts mixes VietQR creation/status endpoints, sandbox test-callback behavior, and user-facing error translation in one API module.
 * Impact: Sandbox callback changes and production payment API changes can affect the same module and complicate testing.
 * Improvement: Separate production payment API calls from sandbox helpers and centralize error mapping in a shared API client layer.
 */

/**
 * Payment API module
 *
 * Coupling Level:
 * - Data Coupling with apiClient because it only passes defined request DTOs
 *   and receives defined response DTOs.
 * - Data Coupling with VietQRPaymentResponse and PaymentStatusResponse types.
 *
 * Cohesion Level:
 * - Functional Cohesion because this module focuses on payment API endpoint access.
 *
 * Reason:
 * This module acts as the single source of API calls for the payments feature.
 * All errors are transformed to user-friendly messages before being thrown.
 * Backend verification, amount validation, and order status transitions remain
 * in backend services (VietQRService, PaymentService).
 */

import { apiClient } from "@/lib/apiClient";
import type {
  CreateVietQRPaymentRequest,
  PaymentStatusResponse,
  VietQRPaymentResponse,
  VietQRTestCallbackRequest,
  VietQRTestCallbackResponse,
} from "./types";

/**
 * Create VietQR QR code for payment
 *
 * @param payload - order_id and amount
 * @returns VietQR payment transaction with QR image URL
 * @throws Error with user-friendly message if creation fails
 */
export async function createVietQRPayment(
  payload: CreateVietQRPaymentRequest
): Promise<VietQRPaymentResponse> {
  try {
    const response = await apiClient<VietQRPaymentResponse>(
      "/payments/vietqr/qr-code/",
      {
        method: "POST",
        body: payload,
      }
    );
    return response;
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed to create QR code";
    throw new Error(`Unable to generate payment QR code: ${message}`);
  }
}

/**
 * Check payment status by transaction ID
 *
 * @param transactionId - transaction ID from create QR response
 * @returns Current payment status
 * @throws Error with user-friendly message if check fails
 */
export async function getPaymentStatus(
  transactionId: string
): Promise<PaymentStatusResponse> {
  try {
    const response = await apiClient<PaymentStatusResponse>(
      `/payments/${transactionId}/status/`,
      {
        method: "GET",
      }
    );
    return response;
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed to check payment status";
    throw new Error(`Unable to check payment status: ${message}`);
  }
}

/**
 * Request VietQR sandbox Test Callback for a generated QR
 *
 * The backend calls VietQR's sandbox test-callback API using the exact
 * content/amount returned by Generate QR.
 *
 * @param payload - payment transaction ID to simulate
 * @returns VietQR test callback response
 * @throws Error with user-friendly message if VietQR test callback fails
 */
export async function requestVietQRTestCallback(
  payload: VietQRTestCallbackRequest
): Promise<VietQRTestCallbackResponse> {
  console.log("[payments/api] requestVietQRTestCallback payload:", payload);

  try {
    const response = await apiClient<VietQRTestCallbackResponse>(
      "/payments/vietqr/test-callback/",
      {
        method: "POST",
        body: payload,
      }
    );
    console.log("[payments/api] requestVietQRTestCallback response:", response);
    return response;
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed to request test callback";
    throw new Error(`Unable to request VietQR test callback: ${message}`);
  }
}
