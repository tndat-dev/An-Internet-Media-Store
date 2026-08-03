/**
 * Component: PaymentStatus
 *
 * Coupling Level:
 * - Data Coupling with PaymentStatusValue type because it receives only status string.
 *
 * Cohesion Level:
 * - Functional Cohesion because this component focuses solely on payment status display.
 *
 * Reason:
 * This component is a pure presentational component that renders payment status text
 * and styling based on input props. It does not call APIs, manage state beyond display,
 * or handle payment business logic. All status determination happens in parent component
 * or backend services.
 */

import type { PaymentStatusValue } from "../types";

export interface PaymentStatusProps {
  status: PaymentStatusValue;
  transactionReference?: string;
  lastCheckedAt?: string;
}

/**
 * Map payment status to user-friendly display text and styling
 */
const statusConfig: Record<
  PaymentStatusValue,
  { label: string; className: string; dotClassName: string }
> = {
  PENDING: {
    label: "Waiting for payment...",
    className: "text-orange-600",
    dotClassName: "bg-orange-500",
  },
  SUCCESS: {
    label: "Payment successful",
    className: "text-green-600",
    dotClassName: "bg-green-500",
  },
  FAILED: {
    label: "Payment failed",
    className: "text-red-600",
    dotClassName: "bg-red-500",
  },
  CANCELLED: {
    label: "Payment cancelled",
    className: "text-gray-600",
    dotClassName: "bg-gray-400",
  },
  REFUNDED: {
    label: "Payment refunded",
    className: "text-blue-600",
    dotClassName: "bg-blue-500",
  },
};

export function PaymentStatus({
  status,
  transactionReference,
  lastCheckedAt,
}: PaymentStatusProps) {
  const config = statusConfig[status];

  return (
    <div className="flex flex-col items-center gap-2 text-center">
      <div className={`inline-flex items-center gap-2 text-sm font-semibold ${config.className}`}>
        <span
          aria-hidden="true"
          className={`h-2.5 w-2.5 rounded-full ${config.dotClassName}`}
        />
        <span>{config.label}</span>
      </div>

      {transactionReference ? (
        <div className="text-xs text-gray-500">
          Ref: <span className="font-semibold text-gray-700">{transactionReference}</span>
        </div>
      ) : null}

      {lastCheckedAt ? (
        <div className="text-xs text-gray-400">Last checked: {lastCheckedAt}</div>
      ) : null}
    </div>
  );
}
