"use client";

import type { Invoice } from "../types";

type InvoiceSummaryProps = {
  invoice: Invoice;
};

function formatCurrency(value: string | number) {
  return `${Number(value).toLocaleString()} VND`;
}

export function InvoiceSummary({ invoice }: InvoiceSummaryProps) {
  /*
   * Coupling/Cohesion: renders invoice data only. Payment initiation and order
   * confirmation stay in the parent screen/API module.
   */
  return (
    <section className="summary-panel invoice-summary">
      {/*
        SOLID Review
        Principle: SRP
        Reason: InvoiceSummary is currently display-only, but any future payment navigation or recalculation added here would mix invoice rendering with checkout workflow.
        Impact: Keeping payment logic out preserves reusability and avoids making this summary harder to test.
        Improvement: Continue passing precomputed invoice totals and leave payment actions in parent orchestration components.
      */}
      <h2>Invoice summary</h2>
      <div className="summary-row">
        <span>Subtotal excluding VAT</span>
        <strong>{formatCurrency(invoice.subtotalExclVat)}</strong>
      </div>
      <div className="summary-row">
        <span>VAT 10%</span>
        <strong>{formatCurrency(invoice.vatAmount)}</strong>
      </div>
      <div className="summary-row">
        <span>Total including VAT</span>
        <strong>{formatCurrency(invoice.totalInclVat)}</strong>
      </div>
      <div className="summary-row">
        <span>Delivery fee</span>
        <strong>{formatCurrency(invoice.deliveryFee)}</strong>
      </div>
      <div className="summary-row summary-total">
        <span>Final payable amount</span>
        <strong>{formatCurrency(invoice.totalAmountToPay)}</strong>
      </div>
    </section>
  );
}
