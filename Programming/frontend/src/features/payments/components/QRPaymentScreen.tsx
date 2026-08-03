"use client";

/**
 * Component: QRPaymentScreen
 *
 * Coupling Level:
 * - Data Coupling with payments API because it sends only order_id and amount
 *   and receives a defined VietQRPaymentResponse DTO.
 * - Stamp Coupling with InvoiceCheckoutData if the component receives a full
 *   invoice object while only order_id and final_payable_amount are used.
 *
 * Cohesion Level:
 * - Functional Cohesion because this component focuses on the VietQR payment user flow:
 *   creating QR, displaying payment information, and checking payment status.
 *
 * Reason:
 * The component renders QR payment information, displays QR image, and provides
 * user-triggered status checks. Backend verification, callback validation, and
 * order status transitions remain in VietQRService and PaymentService.
 * The component does not verify amount, execute callbacks automatically, or
 * transition order state—these responsibilities belong to the backend.
 */

import { useEffect, useRef, useState, type ReactNode } from "react";
import Image from "next/image";
import { useRouter, useSearchParams } from "next/navigation";
import { QRCodeCanvas } from "qrcode.react";
import { OrderProgressStepper } from "@/features/checkout/components/OrderProgressStepper";
import { formatVND } from "@/lib/formatMoney";
import {
  createVietQRPayment,
  getPaymentStatus,
  requestVietQRTestCallback,
} from "../api";
import { markOrderPaid } from "@/features/orders/api";
import type {
  VietQRPaymentResponse,
  VietQRPaymentState,
} from "../types";
import { PaymentStatus } from "./PaymentStatus";

export interface QRScreenProps {
  orderData?: {
    order_id: string;
    final_payable_amount: string;
  };
}

function QRPaymentShell({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <main className="manager-shell">
      <header className="workspace-header">
        <div>
          <p className="eyebrow">Checkout</p>
          <h1>QR Payment</h1>
        </div>
      </header>

      <OrderProgressStepper current="Payment" />
      <section className="qr-payment-layout">{children}</section>
    </main>
  );
}

function QRDisplay({ payment }: { payment: VietQRPaymentResponse }) {
  if (payment.qr_code) {
    return (
      <div className="qr-code-frame">
        <QRCodeCanvas
          value={payment.qr_code}
          size={220}
          level="H"
          includeMargin={true}
        />
      </div>
    );
  }

  if (payment.qr_image_url && !payment.qr_image_url.includes("vietqr")) {
    return (
      <div className="qr-code-frame">
        <Image
          src={payment.qr_image_url}
          alt="Payment QR Code"
          width={220}
          height={220}
          unoptimized
          className="qr-image"
        />
      </div>
    );
  }

  if (payment.qr_link) {
    return (
      <div className="qr-code-frame qr-code-fallback">
        <p className="qr-link-title">QR code hosted by VietQR</p>
        <a
          href={payment.qr_link}
          target="_blank"
          rel="noopener noreferrer"
          className="button button-primary"
        >
          Open Payment Page
        </a>
      </div>
    );
  }

  return (
    <div className="qr-code-frame qr-code-empty">
      <p>Unable to generate a payment QR code.</p>
      <p>Please try again or switch payment method.</p>
    </div>
  );
}

/**
 * QR Payment Screen: Displays QR code and manages payment status checking
 *
 * Flow:
 * 1. Extract order_id and amount from props or query params (fallback for dev)
 * 2. Create VietQR payment transaction and get QR image
 * 3. Display QR code, amount, order ID, transaction reference
 * 4. User can check payment status
 * 5. If status is SUCCESS, redirect to /checkout/success
 * 6. If PENDING/FAILED, allow retry or back to payment method selection
 */
export function QRPaymentScreen({ orderData }: QRScreenProps) {
  const router = useRouter();
  const searchParams = useSearchParams();

  // State management
  const [screenState, setScreenState] = useState<VietQRPaymentState>("idle");
  const [payment, setPayment] = useState<VietQRPaymentResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastCheckedAt, setLastCheckedAt] = useState<string | null>(null);
  const [isCheckingStatus, setIsCheckingStatus] = useState(false);
  const [isRequestingCallback, setIsRequestingCallback] = useState(false);
  const initializedPaymentKeyRef = useRef<string | null>(null);

  // Extract order data from props or fallback to query params
  const orderId =
    orderData?.order_id ||
    searchParams?.get("orderId") ||
    "FALLBACK-ORDER-001";
  const amount =
    orderData?.final_payable_amount || searchParams?.get("amount") || "0";

  // Validate required data
  const hasRequiredData = orderId && amount && amount !== "0";
  const missingOrderError =
    "Missing order information. Please review invoice before payment.";

  /**
   * Initialize: Create QR payment on component mount
   */
  useEffect(() => {
    if (!hasRequiredData) {
      return;
    }

    const paymentKey = `${orderId}:${amount}`;
    if (initializedPaymentKeyRef.current === paymentKey) {
      return;
    }
    initializedPaymentKeyRef.current = paymentKey;

    const initializePayment = async () => {
      setScreenState("creating");
      setError(null);

      try {
        const response = await createVietQRPayment({
          order_id: orderId,
          amount,
        });
        console.log("[QRPaymentScreen] createVietQRPayment response:", response);
        setPayment(response);
        setScreenState("pending");
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to create QR code"
        );
        setScreenState("error");
      }
    };

    initializePayment();
  }, [hasRequiredData, orderId, amount]);

  /**
   * Check payment status
   */
  const handleCheckStatus = async () => {
    if (!payment?.transaction_id) {
      setError("No transaction ID available. Please try again.");
      return;
    }

    setIsCheckingStatus(true);
    setScreenState("checking");

    try {
      const status = await getPaymentStatus(payment.transaction_id);
      setLastCheckedAt(new Date().toLocaleTimeString());
      setPayment((currentPayment) =>
        currentPayment
          ? {
              ...currentPayment,
              status: status.status,
            }
          : currentPayment
      );

      if (status.status === "SUCCESS") {
        // Transition the order to PENDING_PROCESSING now that payment succeeded.
        // Non-fatal if it fails: a retried VietQR callback can reconcile it.
        try {
          await markOrderPaid(status.order_id);
        } catch {
          // Intentionally ignored for the demo flow.
        }
        setScreenState("success");
        // Redirect to success page after brief delay
        setTimeout(() => {
          router.push(
            `/checkout/success?transactionId=${status.transaction_id}`
          );
        }, 1000);
      } else if (status.status === "FAILED" || status.status === "CANCELLED") {
        setScreenState("failed");
        setError(
          "Payment could not be processed. Please try again or select another payment method."
        );
      } else {
        // Status is still PENDING
        setScreenState("pending");
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to check payment status"
      );
      setScreenState("error");
    } finally {
      setIsCheckingStatus(false);
    }
  };

  /**
   * Request VietQR sandbox Test Callback after the user confirms payment
   * Callback failures should NOT block the QR payment flow - they're sandbox test features
   */
  const handlePaymentSubmitted = async () => {
    const buttonDisabled =
      isCheckingStatus || isRequestingCallback || screenState === "checking";

    console.log("[QRPaymentScreen] Toi da thanh toan clicked");
    console.log("[QRPaymentScreen] payment object:", payment);
    console.log(
      "[QRPaymentScreen] payment.transaction_id:",
      payment?.transaction_id
    );
    console.log("[QRPaymentScreen] screenState:", screenState);
    console.log("[QRPaymentScreen] isCheckingStatus:", isCheckingStatus);
    console.log("[QRPaymentScreen] isRequestingCallback:", isRequestingCallback);
    console.log("[QRPaymentScreen] buttonDisabled:", buttonDisabled);

    if (!payment?.transaction_id) {
      console.error(
        "[QRPaymentScreen] Missing transaction_id, returning early",
        payment
      );
      setError("No payment information available.");
      return;
    }

    setIsRequestingCallback(true);
    setScreenState("checking");
    setError(null);

    try {
      await requestVietQRTestCallback({
        transaction_id: payment.transaction_id,
      });

      // VietQR Test Callback calls the configured backend transaction-sync endpoint.
      // Check backend state after requesting the simulation.
      await handleCheckStatus();
    } catch (err) {
      // Test callback failure is NOT a critical error - it's just sandbox simulation
      // Log it but still check status and allow user to proceed
      const callbackError =
        err instanceof Error ? err.message : "Failed to request test callback";
      console.warn("Test callback error (non-critical):", callbackError);

      // Show warning but don't block - user can still manually check status
      setError(
        `Sandbox callback could not be triggered: ${callbackError}. Please wait a moment and try confirming again.`
      );
      setScreenState("pending");
    } finally {
      setIsRequestingCallback(false);
    }
  };

  /**
   * Handle retry: reload page or go back
   */
  const handleRetry = () => {
    window.location.reload();
  };

  const handleBackToPaymentMethod = () => {
    router.push("/checkout/payment");
  };

  const handleBackToInvoice = () => {
    router.push("/checkout/invoice");
  };

  // Error state: missing required data
  if (!hasRequiredData) {
    return (
      <QRPaymentShell>
        <div className="workspace-card qr-feedback-card">
          <h2>Missing Order Information</h2>
          <p>{error || missingOrderError}</p>
          <button
            onClick={handleBackToInvoice}
            className="button button-primary"
          >
            Back to Invoice
          </button>
        </div>
      </QRPaymentShell>
    );
  }

  // Loading state: creating QR
  if (screenState === "creating") {
    return (
      <QRPaymentShell>
        <div className="workspace-card qr-feedback-card">
          <div className="qr-spinner" aria-hidden="true" />
          <h2>Preparing your QR payment</h2>
          <p>Generating QR code...</p>
        </div>
      </QRPaymentShell>
    );
  }

  // Error state: failed to create QR
  if (screenState === "error" && !payment) {
    return (
      <QRPaymentShell>
        <div className="workspace-card qr-feedback-card qr-feedback-error">
          <h2>Payment Error</h2>
          <p>{error}</p>
          <div className="qr-feedback-actions">
            <button onClick={handleRetry} className="button button-primary">
              Retry
            </button>
            <button
              onClick={handleBackToPaymentMethod}
              className="button button-secondary"
            >
              Switch Payment Method
            </button>
          </div>
        </div>
      </QRPaymentShell>
    );
  }

  // Success state: payment confirmed
  if (screenState === "success") {
    return (
      <QRPaymentShell>
        <div className="workspace-card qr-feedback-card qr-feedback-success">
          <div className="qr-feedback-icon" aria-hidden="true">
            ✓
          </div>
          <h2>Payment Successful</h2>
          <p>Redirecting to order confirmation...</p>
        </div>
      </QRPaymentShell>
    );
  }

  // Failed state
  if (screenState === "failed") {
    return (
      <QRPaymentShell>
        <div className="workspace-card qr-feedback-card qr-feedback-error">
          <h2>Payment Failed</h2>
          <p>{error}</p>
          <div className="qr-feedback-actions">
            <button onClick={handleRetry} className="button button-primary">
              Try Again
            </button>
            <button
              onClick={handleBackToPaymentMethod}
              className="button button-secondary"
            >
              Switch Payment Method
            </button>
          </div>
        </div>
      </QRPaymentShell>
    );
  }

  // Main QR display state: pending, checking
  return (
    <QRPaymentShell>
      {/*
        SOLID Review
        Principle: SRP/DIP
        Reason: QRPaymentScreen creates QR payments, polls status, requests sandbox test callbacks, calls order mark-paid, and performs routing in one UI component.
        Impact: UI rendering depends directly on backend workflow details, which makes QR flow tests and payment-provider changes harder.
        Improvement: Move QR payment orchestration to a hook/service and keep this component responsible for rendering QR/status actions.
      */}
      {payment && (
        <article className="qr-payment-card">
          <h2 className="qr-payment-title">Scan to Pay</h2>

          <div className="qr-payment-visual">
            <QRDisplay payment={payment} />
          </div>

          <dl className="qr-payment-summary">
            <div>
              <dt>Amount</dt>
              <dd className="qr-payment-amount">{formatVND(payment.amount)}</dd>
            </div>
            <div>
              <dt>Order ID</dt>
              <dd>{payment.order_id}</dd>
            </div>
            <div>
              <dt>Transaction Reference</dt>
              <dd>{payment.transaction_reference}</dd>
            </div>
          </dl>

          <div className="qr-payment-status">
            <PaymentStatus
              status={payment.status}
              transactionReference={payment.transaction_reference}
              lastCheckedAt={lastCheckedAt || undefined}
            />
          </div>

          {error ? <div className="alert alert-error qr-inline-error">{error}</div> : null}

          <div className="qr-payment-actions">
            <button
              onClick={handleBackToInvoice}
              className="button button-secondary qr-action-back"
            >
              Back
            </button>
            <button
              onClick={handleBackToPaymentMethod}
              className="button button-secondary qr-action-switch"
            >
              Switch Payment Method
            </button>
            <button
              onClick={handlePaymentSubmitted}
              disabled={
                isCheckingStatus ||
                isRequestingCallback ||
                screenState === "checking"
              }
              className="button button-primary qr-action-primary"
            >
              {isRequestingCallback || isCheckingStatus || screenState === "checking"
                ? "Checking..."
                : "I've Paid"}
            </button>
          </div>

          <p className="qr-helper-text">
            Scan the QR code with your banking app, complete the transfer, then
            confirm payment.
          </p>
        </article>
      )}
    </QRPaymentShell>
  );
}
