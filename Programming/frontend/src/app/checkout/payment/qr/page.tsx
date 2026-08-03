"use client";

/**
 * Page: QR Payment
 *
 * Route: /checkout/payment/qr
 *
 * This page displays the QR code for VietQR payment and tracks its status until completion.
 */

import { Suspense, useState } from "react";
import { QRPaymentScreen } from "@/features/payments/components/QRPaymentScreen";
import type { InvoiceCheckoutData } from "@/features/payments/types";

function QRPaymentContent() {
  const [invoiceData] = useState<InvoiceCheckoutData | undefined>(() => {
    if (typeof window === "undefined") {
      return undefined;
    }

    const stored = sessionStorage.getItem("aims.checkout.invoice");
    if (!stored) {
      return undefined;
    }

    try {
      return JSON.parse(stored);
    } catch {
      return undefined;
    }
  });

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <QRPaymentScreen orderData={invoiceData} />
    </div>
  );
}

export default function QRPaymentPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-gray-50 py-8" />}>
      <QRPaymentContent />
    </Suspense>
  );
}
