"use client";

import { useEffect, useState } from "react";

import { listRefundingOrders, markOrderRefunded } from "@/features/orders/api";
import type { ManagerOrder, RefundSummary } from "@/features/orders/types";
import { parseApiError } from "@/lib/apiClient";
import { formatVND } from "@/lib/formatMoney";

// A refund is settled only once the manual bank transfer is confirmed (SUCCESS).
function isRefunded(summary: RefundSummary | null): boolean {
  return summary?.refundStatus === "SUCCESS";
}

export default function ManagerRefundsPage() {
  const [orders, setOrders] = useState<ManagerOrder[]>([]);
  const [page, setPage] = useState(1);
  const [hasNext, setHasNext] = useState(false);
  const [hasPrev, setHasPrev] = useState(false);
  const [status, setStatus] = useState("Loading orders awaiting refund...");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [refundId, setRefundId] = useState<string | null>(null);
  const [refundNote, setRefundNote] = useState("");
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  // Bump to re-run the loader (e.g. after marking refunded) without leaving the page.
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let isCurrent = true;

    async function load() {
      setStatus("Loading orders awaiting refund...");
      try {
        const response = await listRefundingOrders(page);
        if (!isCurrent) {
          return;
        }
        // Stepped past the last page after processing the final order — back up.
        if (response.results.length === 0 && page > 1 && response.count > 0) {
          setPage((current) => Math.max(1, current - 1));
          return;
        }
        setOrders(response.results);
        setHasNext(Boolean(response.next));
        setHasPrev(Boolean(response.previous));
        setStatus("");
      } catch (error) {
        if (isCurrent) {
          setStatus(error instanceof Error ? error.message : "Could not load refunding orders.");
        }
      }
    }

    void load();
    return () => {
      isCurrent = false;
    };
  }, [page, reloadKey]);

  async function confirmRefund() {
    if (!refundId) {
      return;
    }
    const orderId = refundId;
    setBusyId(orderId);
    setMessage(null);
    try {
      await markOrderRefunded(orderId, refundNote.trim());
      setMessage({ text: "Refund marked as completed.", error: false });
      setRefundId(null);
      setRefundNote("");
      setReloadKey((key) => key + 1);
    } catch (error) {
      const fields = parseApiError(error);
      setMessage({ text: fields.refund ?? fields.detail ?? "Could not mark refund.", error: true });
    } finally {
      setBusyId(null);
    }
  }

  return (
    <main className="manager-shell">
      <header className="workspace-header">
        <div>
          <p className="eyebrow">AIMS Manager</p>
          <h1>Refunding orders</h1>
          <p className="lead">
            Cancelled or rejected VietQR orders need a manual refund (no refund API). Transfer the
            funds to the customer, then mark the refund as completed here.
          </p>
        </div>
      </header>

      <section className="workspace-card">
        {message ? <div className={message.error ? "alert alert-error" : "alert"}>{message.text}</div> : null}
        {status ? <div className="alert">{status}</div> : null}

        {!status ? (
          <div className="table-shell">
            <table>
              <thead>
                <tr>
                  <th>Order</th>
                  <th>Processed</th>
                  <th>Customer</th>
                  <th>Total</th>
                  <th>Order status</th>
                  <th>Refund status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((order) => {
                  const isExpanded = expandedId === order.orderId;
                  const isBusy = busyId === order.orderId;
                  const refunded = isRefunded(order.refundSummary);
                  const total = order.invoice?.totalAmountToPay ?? order.totalAmount;
                  const processed = order.processedAt ?? order.updatedAt;
                  return (
                    <FragmentRow key={order.orderId}>
                      <tr>
                        <td>
                          <button
                            type="button"
                            className="table-action"
                            onClick={() => setExpandedId(isExpanded ? null : order.orderId)}
                            aria-expanded={isExpanded}
                          >
                            #{order.orderId.slice(0, 8)}
                          </button>
                        </td>
                        <td>{processed ? new Date(processed).toLocaleString() : "—"}</td>
                        <td>{order.deliveryInfo?.customerName || "—"}</td>
                        <td>{formatVND(total)}</td>
                        <td>
                          <span className={`status-pill status-${order.status.toLowerCase()}`}>
                            {order.status === "REJECTED" ? "REJECTED" : "CANCELLED"}
                          </span>
                        </td>
                        <td>
                          <span className={`status-pill ${refunded ? "status-refunded" : "status-not-refunded"}`}>
                            {refunded ? "Refunded" : "Not refunded"}
                          </span>
                        </td>
                        <td>
                          {refunded ? (
                            <span className="table-subtext">Done{order.refundSummary?.processedBy ? ` · ${order.refundSummary.processedBy}` : ""}</span>
                          ) : (
                            <button
                              type="button"
                              className="button button-primary button-compact"
                              disabled={isBusy}
                              onClick={() => {
                                setRefundId(order.orderId);
                                setRefundNote("");
                              }}
                            >
                              {isBusy ? "..." : "Mark as refunded"}
                            </button>
                          )}
                        </td>
                      </tr>
                      {isExpanded ? (
                        <tr className="order-detail-row">
                          <td colSpan={7}>
                            <OrderDetail order={order} />
                          </td>
                        </tr>
                      ) : null}
                    </FragmentRow>
                  );
                })}
                {orders.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="empty-cell">
                      No orders awaiting a refund.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        ) : null}

        {hasPrev || hasNext ? (
          <nav className="catalog-pagination" aria-label="Order pages">
            <button
              type="button"
              className="button button-secondary"
              disabled={!hasPrev}
              onClick={() => setPage((current) => Math.max(1, current - 1))}
            >
              Previous
            </button>
            <span className="catalog-page-indicator">Page {page}</span>
            <button
              type="button"
              className="button button-secondary"
              disabled={!hasNext}
              onClick={() => setPage((current) => current + 1)}
            >
              Next
            </button>
          </nav>
        ) : null}
      </section>

      {refundId ? (
        <div className="modal-backdrop" role="presentation">
          <section className="modal" role="dialog" aria-modal="true" aria-labelledby="mark-refund-title">
            <h2 id="mark-refund-title">Mark refund as completed</h2>
            <p>
              Confirm only after you have transferred the funds to the customer. Optionally record a
              bank transfer reference for the audit trail.
            </p>
            <label className="field field-wide">
              <span>Note (optional)</span>
              <textarea
                value={refundNote}
                onChange={(event) => setRefundNote(event.target.value)}
                placeholder="e.g. Bank transfer ref #12345"
              />
            </label>
            <div className="modal-actions">
              <button
                type="button"
                className="button button-secondary"
                disabled={busyId !== null}
                onClick={() => {
                  setRefundId(null);
                  setRefundNote("");
                }}
              >
                Cancel
              </button>
              <button type="button" className="button button-primary" disabled={busyId !== null} onClick={confirmRefund}>
                {busyId !== null ? "Saving..." : "Mark as refunded"}
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </main>
  );
}

function paymentMoney(value: string | number | undefined, currency = "VND"): string {
  const amount = Number(value ?? 0).toLocaleString(currency === "VND" ? "vi-VN" : "en-US");
  return `${amount} ${currency}`;
}

function FragmentRow({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

function OrderDetail({ order }: { order: ManagerOrder }) {
  const delivery = order.deliveryInfo;
  return (
    <div className="order-detail">
      <div className="order-detail-items">
        <h3>Items</h3>
        <ul>
          {order.items.map((item) => (
            <li key={item.orderItemId}>
              {item.productTitle} × {item.quantity} — {formatVND(item.lineAmountInclVat)}
            </li>
          ))}
        </ul>
      </div>
      <div className="order-detail-meta">
        <h3>Delivery</h3>
        {delivery ? (
          <dl className="detail-grid">
            <div>
              <dt>Name</dt>
              <dd>{delivery.customerName || "—"}</dd>
            </div>
            <div>
              <dt>Phone</dt>
              <dd>{delivery.phoneNumber || "—"}</dd>
            </div>
            <div>
              <dt>Email</dt>
              <dd>{delivery.email || "—"}</dd>
            </div>
            <div>
              <dt>Province</dt>
              <dd>{delivery.deliveryProvince || "—"}</dd>
            </div>
            <div>
              <dt>Address</dt>
              <dd>{delivery.deliveryAddress || "—"}</dd>
            </div>
          </dl>
        ) : (
          <p className="table-subtext">No delivery info.</p>
        )}
        <RefundSummaryDetails summary={order.refundSummary} />
      </div>
    </div>
  );
}

function RefundSummaryDetails({ summary }: { summary: RefundSummary | null }) {
  if (!summary) {
    return (
      <div className="refund-inline">
        <h3>Payment / Refund</h3>
        <p className="table-subtext">No payment transaction recorded.</p>
      </div>
    );
  }

  return (
    <div className="refund-inline">
      <h3>Payment / Refund</h3>
      <dl className="detail-grid">
        <div>
          <dt>Method</dt>
          <dd>{summary.paymentMethod === "PAYPAL" ? "Card / PayPal" : "VietQR"}</dd>
        </div>
        <div>
          <dt>Payment</dt>
          <dd>{summary.paymentStatus}</dd>
        </div>
        <div>
          <dt>Paid</dt>
          <dd>{paymentMoney(summary.paymentAmount, summary.paymentCurrency)}</dd>
        </div>
        <div>
          <dt>Refund</dt>
          <dd>{summary.refundStatus ?? "Not issued"}</dd>
        </div>
        {summary.refundAmount ? (
          <div>
            <dt>Refund amount</dt>
            <dd>{paymentMoney(summary.refundAmount, summary.paymentCurrency)}</dd>
          </div>
        ) : null}
        {summary.processedBy ? (
          <div>
            <dt>Refunded by</dt>
            <dd>{summary.processedBy}</dd>
          </div>
        ) : null}
        {summary.processedAt ? (
          <div>
            <dt>Refunded at</dt>
            <dd>{new Date(summary.processedAt).toLocaleString()}</dd>
          </div>
        ) : null}
        {summary.manualRefundNote ? (
          <div>
            <dt>Note</dt>
            <dd>{summary.manualRefundNote}</dd>
          </div>
        ) : null}
      </dl>
    </div>
  );
}
