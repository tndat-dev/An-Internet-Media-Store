"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { cancelOrder, getOrder, parseApiError } from "@/features/orders/api";
import type { Order, RefundSummary } from "@/features/orders/types";

const STATUS_LABEL: Record<string, string> = {
  PENDING_PAYMENT: "Pending Payment",
  PENDING_PROCESSING: "Pending Processing",
  APPROVED: "Approved",
  REJECTED: "Rejected",
  CANCELLED: "Cancelled",
};

function money(value: string | number | undefined): string {
  return `${Number(value ?? 0).toLocaleString()} VND`;
}

function paymentMoney(value: string | number | undefined, currency = "VND"): string {
  const amount = Number(value ?? 0).toLocaleString(currency === "VND" ? "vi-VN" : "en-US");
  return `${amount} ${currency}`;
}

function refundText(summary: RefundSummary | null): string {
  if (!summary) return "No payment transaction recorded.";
  if (summary.refundStatus === "SUCCESS" && summary.refundMethod === "PAYPAL_API") {
    return "Refund issued automatically to the original card/PayPal payment.";
  }
  if (summary.refundStatus === "MANUAL_REQUIRED") {
    return "Manual refund required. A product manager must process this refund outside the system.";
  }
  if (summary.refundStatus === "FAILED") {
    return "Refund attempt failed. Please contact support.";
  }
  return "No refund has been issued for this order.";
}

export default function OrderTrackingPage() {
  const params = useParams<{ token: string }>();
  const token = String(params.token);
  const [order, setOrder] = useState<Order | null>(null);
  const [status, setStatus] = useState("Loading order…");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const fetched = await getOrder(token);
        if (active) {
          setOrder(fetched);
          setStatus("");
        }
      } catch {
        if (active) setStatus("Order not found.");
      }
    })();
    return () => {
      active = false;
    };
  }, [token]);

  async function handleCancel() {
    if (!order?.cancelToken) return;
    setBusy(true);
    setMessage(null);
    try {
      const updated = await cancelOrder(order.cancelToken);
      setOrder(updated);
      setMessage({ text: "Your order has been cancelled. A refund will be processed.", error: false });
    } catch (err) {
      setMessage({ text: parseApiError(err).order ?? "Could not cancel this order.", error: true });
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  }

  const canCancel = order?.status === "PENDING_PROCESSING" && Boolean(order?.cancelToken);
  const delivery = order?.deliveryInfo;

  return (
    <main className="manager-shell">
      <header className="workspace-header">
        <div>
          <p className="eyebrow">AIMS Order</p>
          <h1>Order Information</h1>
        </div>
        <Link href="/" className="button button-secondary">
          Back to Home
        </Link>
      </header>

      {status ? <div className="alert">{status}</div> : null}
      {message ? <div className={message.error ? "alert alert-error" : "alert"}>{message.text}</div> : null}

      {order ? (
        <div className="workspace-card">
          <p>
            <strong>Status:</strong>{" "}
            <span className="status-pill status-active">{STATUS_LABEL[order.status] ?? order.status}</span>
          </p>

          {delivery ? (
            <div className="delivery-readonly">
              <p>
                <strong>Recipient:</strong> {delivery.customerName} · {delivery.phoneNumber}
              </p>
              <p>
                <strong>Email:</strong> {delivery.email}
              </p>
              <p>
                <strong>Address:</strong> {delivery.deliveryAddress}, {delivery.deliveryProvince}
              </p>
            </div>
          ) : null}

          <table>
            <thead>
              <tr>
                <th>Product</th>
                <th>Unit price</th>
                <th>Qty</th>
                <th>Item total</th>
              </tr>
            </thead>
            <tbody>
              {order.items.map((item) => (
                <tr key={item.orderItemId}>
                  <td>{item.productTitle}</td>
                  <td>{money(item.unitPrice)}</td>
                  <td>{item.quantity}</td>
                  <td>{money(item.lineAmountInclVat)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {order.invoice ? (
            <div className="summary-panel">
              <div className="summary-row">
                <span>Subtotal (excl. VAT)</span>
                <span>{money(order.invoice.subtotalExclVat)}</span>
              </div>
              <div className="summary-row">
                <span>VAT (10%)</span>
                <span>{money(order.invoice.vatAmount)}</span>
              </div>
              <div className="summary-row">
                <span>Delivery fee</span>
                <span>{money(order.invoice.deliveryFee)}</span>
              </div>
              <div className="summary-total summary-row">
                <span>Total paid</span>
                <span>{money(order.invoice.totalAmountToPay)}</span>
              </div>
            </div>
          ) : null}

          <RefundSummaryPanel summary={order.refundSummary} />

          {canCancel ? (
            <div className="form-actions">
              <button type="button" className="button button-danger" onClick={() => setConfirming(true)} disabled={busy}>
                Cancel Order
              </button>
            </div>
          ) : null}
        </div>
      ) : null}

      {confirming ? (
        <div className="modal-backdrop" role="presentation" onClick={() => setConfirming(false)}>
          <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <h2>Cancel this order?</h2>
            <p className="rule-note">
              This cancels the order before approval. A refund will be issued (card refunds are automatic; VietQR refunds
              are handled manually).
            </p>
            <div className="modal-actions">
              <button type="button" className="button button-secondary" onClick={() => setConfirming(false)} disabled={busy}>
                Keep Order
              </button>
              <button type="button" className="button button-danger" onClick={handleCancel} disabled={busy}>
                {busy ? "Cancelling…" : "Confirm Cancel"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </main>
  );
}

function RefundSummaryPanel({ summary }: { summary: RefundSummary | null }) {
  return (
    <section className="refund-panel">
      <h2>Payment / Refund</h2>
      <p className="rule-note">{refundText(summary)}</p>
      {summary ? (
        <dl className="detail-grid">
          <div>
            <dt>Payment method</dt>
            <dd>{summary.paymentMethod === "PAYPAL" ? "Card / PayPal" : "VietQR"}</dd>
          </div>
          <div>
            <dt>Payment status</dt>
            <dd>{summary.paymentStatus}</dd>
          </div>
          <div>
            <dt>Paid amount</dt>
            <dd>{paymentMoney(summary.paymentAmount, summary.paymentCurrency)}</dd>
          </div>
          {summary.refundStatus ? (
            <div>
              <dt>Refund status</dt>
              <dd>{summary.refundStatus}</dd>
            </div>
          ) : null}
          {summary.refundAmount ? (
            <div>
              <dt>Refund amount</dt>
              <dd>{paymentMoney(summary.refundAmount, summary.refundCurrency ?? "VND")}</dd>
            </div>
          ) : null}
          {summary.refundId ? (
            <div>
              <dt>Refund ID</dt>
              <dd>{summary.refundId}</dd>
            </div>
          ) : null}
        </dl>
      ) : null}
    </section>
  );
}
