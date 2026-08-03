/*
 * SOLID Review
 * Principle: DIP/SRP
 * Reason: paymentApi.ts builds fetch URLs from environment state and exposes concrete PayPal endpoint calls directly to components.
 * Impact: Components depend on concrete HTTP functions, making provider changes and tests more coupled to backend URL structure.
 * Improvement: Wrap these functions behind an injectable payment client and keep URL construction in a shared API adapter.
 */

/**
 * Module: payment/services/paymentApi.ts
 *
 * Coupling Level:
 * - Data Coupling with backend payment endpoints because all API calls send
 *   and receive typed DTOs (InitiatePayPalPaymentRequest,
 *   CapturePayPalPaymentResponse, etc.) — no raw untyped objects.
 * - Data Coupling with PayPalPaymentButton and PaymentResult components
 *   because those components call these functions and receive only the
 *   typed response data they need.
 *
 * Cohesion Level:
 * - Functional Cohesion because this module has one clear purpose:
 *   provide typed HTTP client functions for the payment API endpoints.
 *   Every function here maps to exactly one payment backend endpoint.
 *
 * Reason:
 * Separating API calls into paymentApi.ts keeps components free from
 * fetch/axios logic. Components only import the function they need and
 * receive typed results. This makes backend URL changes or auth header
 * updates a single-file change.
 */

import {
  CapturePayPalPaymentRequest,
  CapturePayPalPaymentResponse,
  InitiatePayPalPaymentRequest,
  InitiatePayPalPaymentResponse,
  RefundPaymentRequest,
  RefundPaymentResponse,
} from "../types/payment";

const RAW_API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";
const API_BASE = RAW_API_BASE.replace(/\/+$/, "");

function paymentApiUrl(path: string): string {
  const apiBase = API_BASE.endsWith("/api") ? API_BASE : `${API_BASE}/api`;
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${apiBase}${normalizedPath}`;
}

async function fetchJson<T>(url: string, options: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.error ?? `HTTP ${response.status}`);
  }

  return response.json() as Promise<T>;
}

/**
 * Initiate a PayPal payment.
 * Returns the approval_url to redirect the buyer to PayPal.
 */
export async function initiatePayPalPayment(
  request: InitiatePayPalPaymentRequest
): Promise<InitiatePayPalPaymentResponse> {
  return fetchJson<InitiatePayPalPaymentResponse>(
    paymentApiUrl("/payments/paypal/initiate/"),
    {
      method: "POST",
      body: JSON.stringify(request),
    }
  );
}

/**
 * Capture a PayPal payment after buyer approval.
 */
export async function capturePayPalPayment(
  request: CapturePayPalPaymentRequest
): Promise<CapturePayPalPaymentResponse> {
  return fetchJson<CapturePayPalPaymentResponse>(
    paymentApiUrl("/payments/paypal/capture/"),
    {
      method: "POST",
      body: JSON.stringify(request),
    }
  );
}

/**
 * Refund a captured PayPal payment.
 */
export async function refundPayment(
  request: RefundPaymentRequest
): Promise<RefundPaymentResponse> {
  return fetchJson<RefundPaymentResponse>(
    paymentApiUrl("/payments/paypal/refund/"),
    {
      method: "POST",
      body: JSON.stringify(request),
    }
  );
}
