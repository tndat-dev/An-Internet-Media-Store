"use client";

import { useEffect, useState } from "react";

import { approveOrder, listPendingOrders, rejectOrder } from "@/features/orders/api";
import type { ManagerOrder, RefundSummary } from "@/features/orders/types";
import { parseApiError } from "@/lib/apiClient";
import { formatVND } from "@/lib/formatMoney";

export default function ManagerOrdersPage() {
  const [orders, setOrders] = useState<ManagerOrder[]>([]);
  const [page, setPage] = useState(1);
  const [hasNext, setHasNext] = useState(false);
  const [hasPrev, setHasPrev] = useState(false);
  const [status, setStatus] = useState("Loading pending orders...");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [rejectId, setRejectId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  // Bump to re-run the loader (e.g. after approve/reject) without leaving the page.
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let isCurrent = true;

    async function load() {
      setStatus("Loading pending orders...");
      try {
        const response = await listPendingOrders(page);
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
          setStatus(error instanceof Error ? error.message : "Could not load pending orders.");
        }
      }
    }

    void load();
    return () => {
      isCurrent = false;
    };
  }, [page, reloadKey]);

  async function handleApprove(orderId: string) {
    setBusyId(orderId);
    setMessage(null);
    try {
      await approveOrder(orderId);
      setMessage({ text: "Order approved.", error: false });
      setReloadKey((key) => key + 1);
    } catch (error) {
      const fields = parseApiError(error);
      setMessage({ text: fields.detail ?? "Could not approve order.", error: true });
    } finally {
      setBusyId(null);
    }
  }

  async function confirmReject() {
    if (!rejectId) {
      return;
    }
    const orderId = rejectId;
    setBusyId(orderId);
    setMessage(null);
    try {
      await rejectOrder(orderId, rejectReason.trim());
      setMessage({ text: "Order rejected; stock restored and refund issued.", error: false });
      setRejectId(null);
      setRejectReason("");
      setReloadKey((key) => key + 1);
    } catch (error) {
      const fields = parseApiError(error);
      setMessage({ text: fields.detail ?? fields.reason ?? "Could not reject order.", error: true });
    } finally {
      setBusyId(null);
    }
  }

  return (
    <main className="manager-shell">
      <header className="workspace-header">
        <div>
          <p className="eyebrow">AIMS Manager</p>
          <h1>Pending orders</h1>
          <p className="lead">Review orders awaiting processing. Approve to fulfil, or reject to restore stock and refund.</p>
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
                  <th>Placed</th>
                  <th>Customer</th>
                  <th>Items</th>
                  <th>Total</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((order) => {
                  const isExpanded = expandedId === order.orderId;
                  const isBusy = busyId === order.orderId;
                  const itemCount = order.items.reduce((sum, item) => sum + item.quantity, 0);
                  const total = order.invoice?.totalAmountToPay ?? order.totalAmount;
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
                        <td>{order.createdAt ? new Date(order.createdAt).toLocaleString() : "—"}</td>
                        <td>{order.deliveryInfo?.customerName || "—"}</td>
                        <td>{itemCount}</td>
                        <td>{formatVND(total)}</td>
                        <td>
                          <div className="table-actions">
                            <button
                              type="button"
                              className="button button-primary button-compact"
                              disabled={isBusy}
                              onClick={() => handleApprove(order.orderId)}
                            >
                              {isBusy ? "..." : "Approve"}
                            </button>
                            <button
                              type="button"
                              className="button button-danger button-compact"
                              disabled={isBusy}
                              onClick={() => {
                                setRejectId(order.orderId);
                                setRejectReason("");
                              }}
                            >
                              Reject
                            </button>
                          </div>
                        </td>
                      </tr>
                      {isExpanded ? (
                        <tr className="order-detail-row">
                          <td colSpan={6}>
                            <OrderDetail order={order} />
                          </td>
                        </tr>
                      ) : null}
                    </FragmentRow>
                  );
                })}
                {orders.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="empty-cell">
                      No pending orders.
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

      {rejectId ? (
        <div className="modal-backdrop" role="presentation">
          <section className="modal" role="dialog" aria-modal="true" aria-labelledby="reject-order-title">
            <h2 id="reject-order-title">Reject order</h2>
            <p>Rejecting restores product stock and issues a refund. Add a reason for the audit trail.</p>
            <label className="field field-wide">
              <span>Reason</span>
              <textarea
                value={rejectReason}
                onChange={(event) => setRejectReason(event.target.value)}
                placeholder="e.g. Out of deliverable area"
              />
            </label>
            <div className="modal-actions">
              <button
                type="button"
                className="button button-secondary"
                disabled={busyId !== null}
                onClick={() => {
                  setRejectId(null);
                  setRejectReason("");
                }}
              >
                Cancel
              </button>
              <button type="button" className="button button-danger" disabled={busyId !== null} onClick={confirmReject}>
                {busyId !== null ? "Rejecting..." : "Reject order"}
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
              <dt>Province</dt>
              <dd>{delivery.deliveryProvince || "—"}</dd>
            </div>
            <div>
              <dt>Address</dt>
              <dd>{delivery.deliveryAddress || "—"}</dd>
            </div>
            <div>
              <dt>Method</dt>
              <dd>{delivery.deliveryMethod || "—"}</dd>
            </div>
          </dl>
        ) : (
          <p className="table-subtext">No delivery info.</p>
        )}
        {order.invoice ? (
          <dl className="detail-grid">
            <div>
              <dt>Subtotal (excl. VAT)</dt>
              <dd>{formatVND(order.invoice.subtotalExclVat)}</dd>
            </div>
            <div>
              <dt>VAT</dt>
              <dd>{formatVND(order.invoice.vatAmount)}</dd>
            </div>
            <div>
              <dt>Delivery fee</dt>
              <dd>{formatVND(order.invoice.deliveryFee)}</dd>
            </div>
            <div>
              <dt>Total</dt>
              <dd>{formatVND(order.invoice.totalAmountToPay)}</dd>
            </div>
          </dl>
        ) : null}
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
    </div>
  );
}
