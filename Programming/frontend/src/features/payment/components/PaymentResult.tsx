/**
 * Component: PaymentResult
 *
 * Coupling Level:
 * - Data Coupling with parent page (PayPalPage/PaymentSuccessPage) because
 *   it receives only the fields it needs to display:
 *   transactionId, capturedAmount, currency, orderId, status.
 *   No large objects or service references are passed in.
 *
 * Cohesion Level:
 * - Functional Cohesion because this component has exactly one purpose:
 *   render the payment result screen (success or failure) after capture.
 *   It does not call any API, process business logic, or manage state
 *   beyond its own UI display toggle.
 *
 * Reason:
 * PaymentResult is a pure display component. Separating it from capture
 * logic (which lives in the PayPal callback page) ensures this component
 * can be reused for any gateway result (PayPal, VietQR) by passing
 * the same props shape.
 */

"use client";

interface PaymentResultProps {
  status: "success" | "failed" | "cancelled";
  orderId: string;
  retryHref?: string;
  transactionId?: string;
  capturedAmount?: number;
  currency?: string;
  transactionDatetime?: string;
  orderTotalVnd?: string;
  customerName?: string;
  phoneNumber?: string;
  shippingAddress?: string;
  deliveryProvince?: string;
}

const STATUS_CONFIG = {
  success: {
    icon: "OK",
    title: "Payment Successful",
    tone: "success",
    message: "Your order is now in pending processing state.",
  },
  failed: {
    icon: "!",
    title: "Payment Failed",
    tone: "danger",
    message: "We could not confirm this payment. You can try PayPal again or choose another method.",
  },
  cancelled: {
    icon: "!",
    title: "Payment Cancelled",
    tone: "warning",
    message: "No money was captured. You can return to payment and complete checkout when ready.",
  },
};

export function PaymentResult({
  status,
  orderId,
  retryHref,
  transactionId,
  capturedAmount,
  currency = "USD",
  transactionDatetime,
  orderTotalVnd,
  customerName,
  phoneNumber,
  shippingAddress,
  deliveryProvince,
}: PaymentResultProps) {
  const config = STATUS_CONFIG[status];

  return (
    <section className={`workspace-card payment-result-card payment-result-${config.tone}`}>
      {/*
        SOLID Review
        Principle: OCP
        Reason: PaymentResult maps status values through a local STATUS_CONFIG, so new result states require modifying this component.
        Impact: Adding more payment outcomes can make the display component grow and risks changing existing status rendering.
        Improvement: Accept display configuration from the caller or move status presentation into a reusable result-state registry.
      */}
      <div className="payment-result-heading">
        <span className="payment-result-icon" aria-hidden="true">
          {config.icon}
        </span>
        <div>
          <p className="eyebrow">Payment Status</p>
          <h1>{config.title}</h1>
          <p className="lead">{config.message}</p>
        </div>
      </div>

      <dl className="payment-result-details">
        <div>
          <dt>Order ID</dt>
          <dd>{orderId}</dd>
        </div>

        {transactionId && (
          <div>
            <dt>Transaction ID</dt>
            <dd>{transactionId}</dd>
          </div>
        )}

        {capturedAmount !== undefined && (
          <div>
            <dt>Amount Paid</dt>
            <dd>
              {capturedAmount.toLocaleString()} {currency}
            </dd>
          </div>
        )}

        {orderTotalVnd && (
          <div>
            <dt>Order Total</dt>
            <dd>
              {Number(orderTotalVnd).toLocaleString("vi-VN")} VND
            </dd>
          </div>
        )}

        {customerName && (
          <div>
            <dt>Customer</dt>
            <dd>{customerName}</dd>
          </div>
        )}

        {phoneNumber && (
          <div>
            <dt>Phone</dt>
            <dd>{phoneNumber}</dd>
          </div>
        )}

        {shippingAddress && (
          <div>
            <dt>Shipping Address</dt>
            <dd>{shippingAddress}</dd>
          </div>
        )}

        {deliveryProvince && (
          <div>
            <dt>Province</dt>
            <dd>{deliveryProvince}</dd>
          </div>
        )}

        {transactionDatetime && (
          <div>
            <dt>Date & Time</dt>
            <dd>
              {new Date(transactionDatetime).toLocaleString("vi-VN")}
            </dd>
          </div>
        )}
      </dl>

      {status === "success" && (
        <p className="payment-result-note">
          Your order is now in <strong>pending processing</strong> state.
          A confirmation email with invoice and transaction details has been sent to you.
        </p>
      )}

      <div className="form-actions payment-result-actions">
        {retryHref && status !== "success" ? (
          <a href={retryHref} className="button button-primary">
            Back to Payment
          </a>
        ) : null}
        <a href="/" className={status === "success" ? "button button-primary" : "button button-secondary"}>
          Back to Home
        </a>
      </div>
    </section>
  );
}
