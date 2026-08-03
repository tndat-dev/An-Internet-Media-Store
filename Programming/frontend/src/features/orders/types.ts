import type { VietnamProvince } from "@/lib/vietnamProvinces";

export type OrderStatus =
  | "PENDING_PAYMENT"
  | "PENDING_PROCESSING"
  | "APPROVED"
  | "REJECTED"
  | "CANCELLED";

export type OrderItem = {
  orderItemId: string;
  productId: string;
  productTitle: string;
  unitPrice: string;
  quantity: number;
  lineAmountExclVat: string;
  lineAmountInclVat: string;
};

export type DeliveryInfo = {
  deliveryInfoId: string;
  customerName: string;
  phoneNumber: string;
  email: string;
  deliveryProvince: string;
  deliveryAddress: string;
  deliveryMethod: string;
  deliveryInstructions: string;
  shippingFee: string;
};

export type InvoiceTotals = {
  invoiceId: string;
  subtotalExclVat: string;
  vatAmount: string;
  totalInclVat: string;
  deliveryFee: string;
  totalAmountToPay: string;
};

export type RefundSummary = {
  paymentMethod: "PAYPAL" | "VIETQR";
  paymentStatus: "PENDING" | "SUCCESS" | "FAILED" | "REFUNDED" | "CANCELLED";
  paymentAmount: string;
  paymentCurrency: string;
  captureId?: string;
  refundId?: string;
  refundStatus?: "PENDING" | "SUCCESS" | "FAILED" | "MANUAL_REQUIRED";
  refundMethod?: "PAYPAL_API" | "MANUAL_BANK_TRANSFER";
  refundAmount?: string;
  refundCurrency?: string;
  refundReason?: string;
  manualRefundNote?: string;
  processedBy?: string | null;
  processedAt?: string | null;
  createdAt?: string | null;
};

export type Order = {
  orderId: string;
  orderToken: string;
  cancelToken?: string;
  status: OrderStatus;
  totalAmount: string;
  items: OrderItem[];
  deliveryInfo: DeliveryInfo | null;
  invoice: InvoiceTotals | null;
  refundSummary: RefundSummary | null;
  createdAt?: string;
  updatedAt?: string;
};

export type DeliveryPreview = {
  subtotalExclVat: string;
  vatAmount: string;
  totalInclVat: string;
  deliveryFee: string;
  totalAmountToPay: string;
};

export type Invoice = InvoiceTotals & {
  orderId: string;
  orderToken: string;
  status: OrderStatus;
  items: OrderItem[];
  deliveryInfo: DeliveryInfo;
};

export type DeliveryInfoPayload = {
  customerName: string;
  phoneNumber: string;
  email: string;
  deliveryProvince: VietnamProvince | "";
  deliveryAddress: string;
  deliveryMethod: "STANDARD" | "EXPRESS";
  deliveryInstructions: string;
};

// Manager review queue view — adds who/when processed (ManagerOrderSerializer).
export type ManagerOrder = Order & {
  processedAt: string | null;
  processedBy: string | null;
};

// Mirrors DRF PageNumberPagination response shape.
export type PaginatedOrders<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};
