/**
 * Page: /checkout/payment/card
 *
 * Coupling Level:
 * - Data Coupling with PayPalPaymentButton because this page passes only
 *   the props the button needs (orderId, amount, currency, returnUrl, cancelUrl).
 * - Data Coupling with capturePayPalPayment API function because the callback
 *   handler passes only provider_order_id and internal_order_id — primitives
 *   read directly from URL query params.
 * - Data Coupling with PaymentResult because it receives only the display fields
 *   (status, transactionId, capturedAmount, currency, orderId).
 *
 * Cohesion Level:
 * - Procedural Cohesion (acceptable for a page/orchestration component)
 *   because this page coordinates a sequence of steps:
 *   1. Show PayPal payment button
 *   2. Handle PayPal return callback (capture the payment)
 *   3. Show the payment result
 *   Each step is delegated to a focused child component or API function.
 *
 * Reason:
 * Pages naturally have procedural cohesion as they orchestrate flows.
 * Business logic lives in paymentApi.ts and PaymentService (backend), not here.
 * This page only reads query params, calls the capture API, and passes results
 * to PaymentResult. window.location is never accessed during SSR — base URL
 * is read from NEXT_PUBLIC_BASE_URL env var to avoid ReferenceError in Node.js.
 */

"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { OrderProgressStepper } from "@/features/checkout/components/OrderProgressStepper";
import { PayPalPaymentButton } from "@/features/payment/components/PayPalPaymentButton";
import { PaymentResult } from "@/features/payment/components/PaymentResult";
import { capturePayPalPayment } from "@/features/payment/services/paymentApi";
import { CapturePayPalPaymentResponse } from "@/features/payment/types/payment";
import { formatVND } from "@/lib/formatMoney";

type PageState = "idle" | "capturing" | "success" | "failed" | "cancelled";

// Read base URL from env — never use window.location.origin (crashes SSR)
const BASE_URL = process.env.NEXT_PUBLIC_BASE_URL ?? "http://localhost:3000";
const CARD_PAYMENT_PATH = "/checkout/payment/card";

function PayPalPaymentInner() {
  const searchParams = useSearchParams();
  const [pageState, setPageState] = useState<PageState>("idle");
  const [captureResult, setCaptureResult] = useState<CapturePayPalPaymentResponse | null>(null);
  const [captureError, setCaptureError] = useState<string | null>(null);

  // Core order params passed via query string from checkout flow
  const orderId = searchParams.get("order_id") ?? "";
  const amountVnd = searchParams.get("amount_vnd") ?? "";
  const paypalCurrency = process.env.NEXT_PUBLIC_PAYPAL_CURRENCY ?? "USD";

  // PayPal injects these on return after buyer action
  const providerOrderId = searchParams.get("token");   // present on both approve & cancel
  const payerAction = searchParams.get("PayerID");     // present only on approval
  const cancelFlag = searchParams.get("cancelled");    // our own cancel marker
  const capturedFlag = searchParams.get("captured");
  const captureTransactionId = searchParams.get("transaction_id");
  const capturedAmount = searchParams.get("captured_amount");
  const capturedCurrency = searchParams.get("captured_currency");
  const orderTotalVnd = searchParams.get("order_total_vnd");
  const customerName = searchParams.get("customer_name");
  const phoneNumber = searchParams.get("phone_number");
  const shippingAddress = searchParams.get("shipping_address");
  const deliveryProvince = searchParams.get("delivery_province");

  const returnUrl =
    `${BASE_URL}${CARD_PAYMENT_PATH}` +
    `?order_id=${orderId}&amount_vnd=${amountVnd}`;
  const cancelUrl =
    `${BASE_URL}${CARD_PAYMENT_PATH}` +
    `?order_id=${orderId}&amount_vnd=${amountVnd}&cancelled=true`;
  const paymentMethodHref = `/checkout/payment?orderId=${encodeURIComponent(orderId)}&amount=${encodeURIComponent(amountVnd)}`;

  const completedCapture = useMemo<CapturePayPalPaymentResponse | null>(
    () =>
      capturedFlag === "1" && captureTransactionId
        ? {
            transaction_id: captureTransactionId,
            captured_amount: capturedAmount ? Number(capturedAmount) : undefined,
            captured_currency: capturedCurrency ?? undefined,
            order_total_vnd: orderTotalVnd ?? undefined,
            customer_name: customerName ?? undefined,
            phone_number: phoneNumber ?? undefined,
            shipping_address: shippingAddress ?? undefined,
            delivery_province: deliveryProvince ?? undefined,
          }
        : null,
    [
      capturedAmount,
      capturedCurrency,
      capturedFlag,
      captureTransactionId,
      customerName,
      deliveryProvince,
      orderTotalVnd,
      phoneNumber,
      shippingAddress,
    ],
  );

  // Auto-capture when PayPal redirects back after buyer approval
  useEffect(() => {
    if (completedCapture || !providerOrderId || !payerAction) {
      return;
    }

    let active = true;
    capturePayPalPayment({
        provider_order_id: providerOrderId,
        internal_order_id: orderId,
      })
      .then((result) => {
        if (!active) return;
        setCaptureResult(result);
        setPageState("success");
      })
      .catch((err: unknown) => {
        if (!active) return;
        setCaptureError(err instanceof Error ? err.message : "Capture failed.");
        setPageState("failed");
      });

    return () => {
      active = false;
    };
  }, [completedCapture, orderId, payerAction, providerOrderId]);

  const effectiveState: PageState = completedCapture
    ? "success"
    : cancelFlag
      ? "cancelled"
      : providerOrderId && payerAction && pageState === "idle"
        ? "capturing"
        : pageState;
  const effectiveCaptureResult = completedCapture ?? captureResult;

  // ---- Render states ----

  if (effectiveState === "capturing") {
    return (
      <main className="manager-shell">
        <section className="workspace-card payment-state-card">
          <p className="rule-note">Processing your payment...</p>
        </section>
      </main>
    );
  }

  if (effectiveState === "success" && (effectiveCaptureResult || captureTransactionId)) {
    const result = effectiveCaptureResult ?? {
      transaction_id: captureTransactionId ?? "",
    };

    return (
      <main className="manager-shell">
        <PaymentResult
          status="success"
          orderId={orderId}
          transactionId={result.transaction_id}
          capturedAmount={result.captured_amount}
          currency={result.captured_currency ?? paypalCurrency}
          transactionDatetime={new Date().toISOString()}
          orderTotalVnd={result.order_total_vnd ?? amountVnd}
          customerName={result.customer_name}
          phoneNumber={result.phone_number}
          shippingAddress={result.shipping_address}
          deliveryProvince={result.delivery_province}
        />
      </main>
    );
  }

  if (effectiveState === "failed") {
    return (
      <main className="manager-shell">
        <PaymentResult status="failed" orderId={orderId} retryHref={paymentMethodHref} />
        {captureError && (
          <p className="alert alert-error">{captureError}</p>
        )}
      </main>
    );
  }

  if (effectiveState === "cancelled") {
    return (
      <main className="manager-shell">
        <PaymentResult status="cancelled" orderId={orderId} retryHref={paymentMethodHref} />
      </main>
    );
  }

  // Default: show PayPal payment button
  return (
    <main className="manager-shell paypal-page">
      {/*
        SOLID Review
        Principle: SRP
        Reason: PayPalPaymentInner reads provider query params, builds return/cancel URLs, captures approved payments, maps result data, and renders multiple page states.
        Impact: Routing concerns, payment orchestration, and result presentation are coupled, increasing maintenance cost as PayPal flow changes.
        Improvement: Extract query parsing and capture orchestration into a hook, then render based on a simple view model.
      */}
      <header className="workspace-header">
        <div>
          <p className="eyebrow">Checkout</p>
          <h1>Pay with Card / PayPal</h1>
          <p className="lead">Complete this payment securely with PayPal Sandbox.</p>
        </div>
        <Link
          className="button button-secondary"
          href={paymentMethodHref}
        >
          Back to Payment
        </Link>
      </header>

      <OrderProgressStepper current="Payment" />

      <section className="paypal-layout">
        <div className="workspace-card paypal-main-panel">
          <h2>Card Payment</h2>
          <p className="rule-note">
            Card payment is handled by PayPal Sandbox. The charge amount is calculated by the backend from the saved invoice.
          </p>

          <PayPalPaymentButton
            orderId={orderId}
            currency={paypalCurrency}
            returnUrl={returnUrl}
            cancelUrl={cancelUrl}
            description={`AIMS Order ${orderId}`}
          />
        </div>

        <aside className="payment-summary-panel">
          <h2>Order Summary</h2>
          <dl className="payment-summary-list">
            <div>
              <dt>Order ID</dt>
              <dd>{orderId || "-"}</dd>
            </div>
            <div className="payment-summary-total">
              <dt>Total Payable</dt>
              <dd>{amountVnd ? formatVND(amountVnd) : "Server calculated"}</dd>
            </div>
          </dl>
          <div className="payment-security-note">
            <span aria-hidden="true">LOCK</span>
            <p>Your payment information is securely processed by PayPal Sandbox.</p>
          </div>
        </aside>
      </section>
    </main>
  );
}

// useSearchParams() must be inside a Suspense boundary for static prerender (Next 16).
export default function PayPalPaymentPage() {
  return (
    <Suspense
      fallback={
        <main className="manager-shell">
          <section className="workspace-card payment-state-card">
            <p className="rule-note">Loading payment...</p>
          </section>
        </main>
      }
    >
      <PayPalPaymentInner />
    </Suspense>
  );
}
