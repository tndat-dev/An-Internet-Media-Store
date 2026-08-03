"use client";

import { Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { OrderProgressStepper } from "@/features/checkout/components/OrderProgressStepper";
import { formatVND } from "@/lib/formatMoney";

type PaymentMethod = "vietqr" | "paypal";

function PaymentMethodContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [selectedMethod, setSelectedMethod] = useState<PaymentMethod>("vietqr");

  const orderId = searchParams?.get("orderId") ?? "";
  const amount = searchParams?.get("amount") ?? "";
  const isReady = Boolean(orderId && amount);

  const query = new URLSearchParams();
  if (orderId) query.set("orderId", orderId);
  if (amount) query.set("amount", amount);
  const qrHref = `/checkout/payment/qr?${query.toString()}`;
  const paypalHref = `/checkout/payment/card?order_id=${encodeURIComponent(orderId)}&amount_vnd=${encodeURIComponent(amount)}`;

  function handleContinue() {
    if (!isReady) {
      return;
    }
    router.push(selectedMethod === "vietqr" ? qrHref : paypalHref);
  }

  return (
    <main className="manager-shell payment-method-page">
      <header className="workspace-header">
        <div>
          <p className="eyebrow">Checkout</p>
          <h1>Payment Method</h1>
          <p className="lead">Choose how you would like to pay for this order.</p>
        </div>
        <Link className="button button-secondary" href="/checkout/invoice">
          Back to Invoice
        </Link>
      </header>

      <OrderProgressStepper current="Payment" />

      {!isReady ? <p className="alert alert-error">Confirm the invoice first to load order details.</p> : null}

      <section className="payment-method-layout" aria-label="Payment method selection">
        <div className="payment-method-main">
          <h2>Select Payment Method</h2>

          <div className="payment-option-list" role="radiogroup" aria-label="Payment methods">
            <button
              type="button"
              className={`payment-option ${selectedMethod === "vietqr" ? "is-selected" : ""}`}
              disabled={!isReady}
              onClick={() => setSelectedMethod("vietqr")}
              role="radio"
              aria-checked={selectedMethod === "vietqr"}
            >
              <span className="payment-option-icon" aria-hidden="true">
                QR
              </span>
              <span className="payment-option-copy">
                <strong>QR Code Payment</strong>
                <span>Scan to pay with banking app</span>
              </span>
              <span className="payment-option-radio" aria-hidden="true" />
            </button>

            <button
              type="button"
              className={`payment-option ${selectedMethod === "paypal" ? "is-selected" : ""}`}
              disabled={!isReady}
              onClick={() => setSelectedMethod("paypal")}
              role="radio"
              aria-checked={selectedMethod === "paypal"}
            >
              <span className="payment-option-icon" aria-hidden="true">
                PP
              </span>
              <span className="payment-option-copy">
                <strong>Card Payment</strong>
                <span>Pay via credit/debit card or PayPal Sandbox</span>
              </span>
              <span className="payment-option-radio" aria-hidden="true" />
            </button>
          </div>
        </div>

        <aside className="payment-summary-panel" aria-label="Order summary">
          <h2>Order Summary</h2>
          <dl className="payment-summary-list">
            <div>
              <dt>Order ID</dt>
              <dd>{orderId || "-"}</dd>
            </div>
            <div className="payment-summary-total">
              <dt>Total Payable</dt>
              <dd>{amount ? formatVND(amount) : "-"}</dd>
            </div>
          </dl>
          <div className="payment-security-note">
            <span aria-hidden="true">LOCK</span>
            <p>Your payment information is securely processed. We do not store card details.</p>
          </div>
        </aside>
      </section>

      <div className="payment-method-actions">
        <Link className="button button-secondary" href="/checkout/invoice">
          Back
        </Link>
        <button type="button" className="button button-primary" disabled={!isReady} onClick={handleContinue}>
          Continue
        </button>
      </div>
    </main>
  );
}

export default function PaymentMethodPage() {
  return (
    <Suspense fallback={<main className="manager-shell">Loading…</main>}>
      <PaymentMethodContent />
    </Suspense>
  );
}
