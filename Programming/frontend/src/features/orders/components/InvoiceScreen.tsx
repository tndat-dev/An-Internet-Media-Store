"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { OrderProgressStepper } from "@/features/checkout/components/OrderProgressStepper";

import { confirmOrder, getInvoice } from "../api";
import type { Invoice } from "../types";
import { InvoiceSummary } from "./InvoiceSummary";

function formatCurrency(value: string | number) {
  return `${Number(value).toLocaleString()} VND`;
}

function getCurrentOrderId() {
  if (typeof window === "undefined") {
    return "";
  }
  return window.localStorage.getItem("aims-current-order-id") ?? "";
}

export function InvoiceScreen() {
  /*
   * Coupling/Cohesion: loads invoice details and initiates order confirmation.
   * It does not calculate totals itself; it delegates that concern to the
   * backend invoice API and renders only the payment navigation flow.
   */
  const router = useRouter();
  const [invoice, setInvoice] = useState<Invoice | null>(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isConfirming, setIsConfirming] = useState(false);

  useEffect(() => {
    const orderId = getCurrentOrderId();
    const invoiceRequest = orderId
      ? getInvoice(orderId)
      : Promise.reject(new Error("Create a draft order from the cart before reviewing invoice."));

    invoiceRequest
      .then(setInvoice)
      .catch((loadError) => setError(loadError instanceof Error ? loadError.message : "Could not load invoice."))
      .finally(() => setIsLoading(false));
  }, []);

  async function handleProceedToPayment() {
    if (!invoice) {
      return;
    }
    setIsConfirming(true);
    setError("");
    try {
      const order = await confirmOrder(invoice.orderId);
      const amount = order.invoice?.totalAmountToPay ?? invoice.totalAmountToPay;
      router.push(`/checkout/payment?orderId=${order.orderId}&orderToken=${order.orderToken}&amount=${amount}`);
    } catch (confirmError) {
      setError(confirmError instanceof Error ? confirmError.message : "Could not confirm order.");
    } finally {
      setIsConfirming(false);
    }
  }

  return (
    <main className="manager-shell">
      {/*
        SOLID Review
        Principle: SRP
        Reason: InvoiceScreen loads invoice data, renders order/delivery details, confirms the order, and routes into payment selection.
        Impact: Invoice presentation and checkout workflow orchestration can change for different reasons but are coupled in one screen.
        Improvement: Move invoice loading/confirmation into a checkout hook and keep the screen focused on composition.
      */}
      <header className="workspace-header">
        <div>
          <p className="eyebrow">Checkout</p>
          <h1>Invoice</h1>
          <p className="lead">Review product totals, VAT, delivery fee, and final payable amount.</p>
        </div>
        <Link className="button button-secondary" href="/checkout/delivery">
          Back
        </Link>
      </header>

      <OrderProgressStepper current="Invoice" />

      {error ? <div className="alert alert-error">{error}</div> : null}
      {isLoading ? <div className="workspace-card">Loading invoice...</div> : null}

      {invoice ? (
        <section className="workspace-card checkout-grid">
          <div className="checkout-main">
            <h2>Items</h2>
            <div className="table-shell">
              <table>
                <thead>
                  <tr>
                    <th>Product</th>
                    <th>Unit price</th>
                    <th>Quantity</th>
                    <th>Item total</th>
                  </tr>
                </thead>
                <tbody>
                  {invoice.items.map((item) => (
                    <tr key={item.orderItemId}>
                      <td>{item.productTitle}</td>
                      <td>{formatCurrency(item.unitPrice)}</td>
                      <td>{item.quantity}</td>
                      <td>{formatCurrency(item.lineAmountExclVat)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="delivery-readonly">
              <h2>Delivery</h2>
              <p>
                <strong>{invoice.deliveryInfo.customerName}</strong> - {invoice.deliveryInfo.phoneNumber}
              </p>
              <p>
                {invoice.deliveryInfo.deliveryAddress}, {invoice.deliveryInfo.deliveryProvince}
              </p>
              <p>{invoice.deliveryInfo.email}</p>
            </div>
          </div>

          <aside>
            <InvoiceSummary invoice={invoice} />
            <button
              type="button"
              className="button button-primary full-width"
              disabled={isConfirming}
              onClick={handleProceedToPayment}
            >
              {isConfirming ? "Preparing payment..." : "Proceed to Payment"}
            </button>
          </aside>
        </section>
      ) : null}
    </main>
  );
}
