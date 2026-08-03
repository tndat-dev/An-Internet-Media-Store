"use client";

/**
 * Page: Order Result (/checkout/success) - reached after VietQR/PayPal success.
 *
 * Shows the payment result, the order's customer/delivery info + real status
 * (fetched via the stored order view token), and the transaction details, per
 * the OrderResult mockup. Read-only.
 */

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { OrderProgressStepper } from "@/features/checkout/components/OrderProgressStepper";
import { getOrder } from "@/features/orders/api";
import type { Order } from "@/features/orders/types";
import { getPaymentStatus } from "@/features/payments/api";
import type { PaymentStatusResponse } from "@/features/payments/types";
import { getOrderToken } from "@/lib/checkoutStorage";

const STATUS_LABEL: Record<string, string> = {
  PENDING_PROCESSING: "Pending Processing",
  PENDING_PAYMENT: "Pending Payment",
  APPROVED: "Approved",
  REJECTED: "Rejected",
  CANCELLED: "Cancelled",
};

function money(value: string | number | undefined, currency = "VND"): string {
  const locale = currency === "VND" ? "vi-VN" : "en-US";
  return `${Number(value ?? 0).toLocaleString(locale)} ${currency}`;
}

function CheckoutSuccessContent() {
  const searchParams = useSearchParams();
  const transactionId = searchParams?.get("transactionId");

  const [payment, setPayment] = useState<PaymentStatusResponse | null>(null);
  const [order, setOrder] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    (async () => {
      try {
        let shouldUseStoredToken = true;

        if (transactionId) {
          const details = await getPaymentStatus(transactionId);
          if (active) setPayment(details);

          if (details.order_token) {
            shouldUseStoredToken = false;
            try {
              const fetched = await getOrder(details.order_token);
              if (active) setOrder(fetched);
            } catch {
              /* order lookup is best-effort */
            }
          }
        }

        const token = getOrderToken();
        if (shouldUseStoredToken && token) {
          try {
            const fetched = await getOrder(token);
            if (active) setOrder(fetched);
          } catch {
            /* order lookup is best-effort */
          }
        }

        if (!transactionId) {
          setError("No transaction found. Please contact support.");
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Failed to load payment details.");
        }
      } finally {
        if (active) setLoading(false);
      }
    })();

    return () => {
      active = false;
    };
  }, [transactionId]);

  if (loading) {
    return (
      <main className="manager-shell">
        <p className="alert">Loading order confirmation...</p>
      </main>
    );
  }

  const orderStatus = order
    ? STATUS_LABEL[order.status] ?? order.status
    : payment?.order_status
      ? STATUS_LABEL[payment.order_status] ?? payment.order_status
      : "Pending Processing";
  const delivery = order?.deliveryInfo;
  const orderToken = payment?.order_token ?? order?.orderToken ?? getOrderToken();

  return (
    <main className="manager-shell">
      <header className="workspace-header">
        <div>
          <p className="eyebrow">AIMS Checkout</p>
          <h1>Order Result</h1>
        </div>
      </header>

      <OrderProgressStepper current="Result" />

      {error && !payment ? <div className="alert alert-error">{error}</div> : null}

      <div className="workspace-card result-card">
        <div className="result-status">
          <span className="result-check" aria-hidden="true">
            {"\u2713"}
          </span>
          <h2>Payment Successful</h2>
          <span className="status-pill status-active">{orderStatus}</span>
        </div>

        {delivery ? (
          <section className="result-section">
            <h3>Order Information</h3>
            <div className="form-grid">
              <p>
                <strong>Customer:</strong> {delivery.customerName}
              </p>
              <p>
                <strong>Phone:</strong> {delivery.phoneNumber}
              </p>
              <p className="field-wide">
                <strong>Shipping address:</strong> {delivery.deliveryAddress}, {delivery.deliveryProvince}
              </p>
            </div>
          </section>
        ) : null}

        {payment ? (
          <section className="result-section">
            <h3>Transaction Details</h3>
            <div className="summary-panel">
              <div className="summary-row">
                <span>Total amount paid</span>
                <span>{money(payment.amount, payment.currency)}</span>
              </div>
              <div className="summary-row">
                <span>Payment method</span>
                <span>{payment.payment_method === "VIETQR" ? "QR Code (VietQR)" : "PayPal"}</span>
              </div>
              <div className="summary-row">
                <span>Transaction ID</span>
                <span>{payment.transaction_id}</span>
              </div>
              {payment.transaction_reference ? (
                <div className="summary-row">
                  <span>Reference</span>
                  <span>{payment.transaction_reference}</span>
                </div>
              ) : null}
            </div>
          </section>
        ) : null}

        <div className="form-actions">
          {orderToken ? (
            <Link href={`/orders/${orderToken}`} className="button button-secondary">
              View Order Information
            </Link>
          ) : null}
          <Link href="/" className="button button-primary">
            Back to Home
          </Link>
        </div>
      </div>
    </main>
  );
}

export default function CheckoutSuccessPage() {
  return (
    <Suspense
      fallback={
        <main className="manager-shell">
          <p className="alert">Loading order confirmation...</p>
        </main>
      }
    >
      <CheckoutSuccessContent />
    </Suspense>
  );
}
