"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { OrderProgressStepper } from "@/features/checkout/components/OrderProgressStepper";
import { getCart } from "@/features/carts/api";
import type { Cart, CartStockError } from "@/features/carts/types";
import { ApiError, parseApiError } from "@/lib/apiClient";
import { VIETNAM_PROVINCES } from "@/lib/vietnamProvinces";

import { previewDelivery, submitDeliveryInfo } from "../api";
import type { DeliveryInfoPayload, DeliveryPreview } from "../types";

function money(value: string | number | undefined): string {
  return `${Number(value ?? 0).toLocaleString()} VND`;
}

function stockErrorMessage(error: CartStockError) {
  return `${error.productTitle ?? "This item"} only has ${error.availableQuantity ?? 0} unit(s) available; remove ${error.missingQuantity ?? 0} unit(s) before continuing.`;
}

const initialForm: DeliveryInfoPayload = {
  customerName: "",
  phoneNumber: "",
  email: "",
  deliveryProvince: "",
  deliveryAddress: "",
  deliveryMethod: "STANDARD",
  deliveryInstructions: "",
};

const fieldMap: Record<string, keyof DeliveryInfoPayload> = {
  name: "customerName",
  phone: "phoneNumber",
  email: "email",
  province: "deliveryProvince",
  address: "deliveryAddress",
  deliveryMethod: "deliveryMethod",
};

function getCurrentOrderId() {
  if (typeof window === "undefined") {
    return "";
  }
  return window.localStorage.getItem("aims-current-order-id") ?? "";
}

export function DeliveryInfoForm() {
  /*
   * Coupling/Cohesion: owns delivery form state and UX validation display only.
   * Backend validators remain the source of truth for accepted delivery data.
   */
  const router = useRouter();
  const [form, setForm] = useState<DeliveryInfoPayload>(initialForm);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<keyof DeliveryInfoPayload, string>>>({});
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [preview, setPreview] = useState<DeliveryPreview | null>(null);
  const [cart, setCart] = useState<Cart | null>(null);
  const [cartStatus, setCartStatus] = useState("Loading cart summary...");

  useEffect(() => {
    let active = true;
    getCart()
      .then((currentCart) => {
        if (active) {
          setCart(currentCart);
          setCartStatus("");
        }
      })
      .catch((loadError) => {
        if (active) {
          setCartStatus(loadError instanceof Error ? loadError.message : "Could not load cart summary.");
        }
      });
    return () => {
      active = false;
    };
  }, []);

  // Live Order Summary: recompute delivery fee + totals when province/method
  // change (debounced). Mirrors the mockup's dynamic summary; backend is source
  // of truth for the weight-based fee.
  useEffect(() => {
    const orderId = getCurrentOrderId();
    const province = form.deliveryProvince.trim();
    if (!orderId || !province) {
      return;
    }
    let active = true;
    const handle = setTimeout(async () => {
      try {
        const result = await previewDelivery(orderId, province, form.deliveryMethod);
        if (active) setPreview(result);
      } catch {
        if (active) setPreview(null);
      }
    }, 400);
    return () => {
      active = false;
      clearTimeout(handle);
    };
  }, [form.deliveryProvince, form.deliveryMethod]);

  function updateField<K extends keyof DeliveryInfoPayload>(field: K, value: DeliveryInfoPayload[K]) {
    setForm((current) => ({
      ...current,
      [field]: value,
    }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setFieldErrors({});
    setIsSubmitting(true);

    const orderId = getCurrentOrderId();
    if (!orderId) {
      setError("Create a draft order from the cart before entering delivery information.");
      setIsSubmitting(false);
      return;
    }

    try {
      await submitDeliveryInfo(orderId, form);
      router.push("/checkout/invoice");
    } catch (submitError) {
      if (submitError instanceof ApiError) {
        const payload = submitError.body as { cart?: CartStockError[] } | null;
        if (Array.isArray(payload?.cart) && payload.cart.length > 0) {
          setError(`Stock changed after you entered delivery information. Return to cart and update it: ${payload.cart.map(stockErrorMessage).join(" ")}`);
          return;
        }
      }
      const apiErrors = parseApiError(submitError);
      const nextFieldErrors: Partial<Record<keyof DeliveryInfoPayload, string>> = {};
      for (const [apiField, message] of Object.entries(apiErrors)) {
        const field = fieldMap[apiField];
        if (field) {
          nextFieldErrors[field] = message;
        }
      }
      setFieldErrors(nextFieldErrors);
      setError(submitError instanceof Error ? submitError.message : "Could not save delivery information.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="manager-shell">
      {/*
        SOLID Review
        Principle: SRP
        Reason: DeliveryInfoForm manages delivery form state, API error mapping, live delivery preview, submission, and navigation in one component.
        Impact: Delivery validation UX and checkout fee-preview behavior are harder to evolve independently.
        Improvement: Extract delivery form state, error mapping, and preview fetching into focused hooks.
      */}
      <header className="workspace-header">
        <div>
          <p className="eyebrow">Checkout</p>
          <h1>Delivery Information</h1>
          <p className="lead">Enter the recipient and address used to calculate the invoice.</p>
        </div>
        <Link className="button button-secondary" href="/cart">
          Back to Cart
        </Link>
      </header>

      <OrderProgressStepper current="Delivery" />

      <form className="workspace-card product-form" onSubmit={handleSubmit}>
        {error ? <div className="alert alert-error">{error}</div> : null}

        <fieldset className="form-section">
          <legend>Recipient</legend>
          <div className="form-grid">
            <label className="field">
              <span>Recipient name</span>
              <input
                className={fieldErrors.customerName ? "input-error" : ""}
                value={form.customerName}
                onChange={(event) => updateField("customerName", event.target.value)}
                required
              />
              {fieldErrors.customerName ? <small className="field-error">{fieldErrors.customerName}</small> : null}
            </label>
            <label className="field">
              <span>Phone number</span>
              <input
                className={fieldErrors.phoneNumber ? "input-error" : ""}
                value={form.phoneNumber}
                onChange={(event) => updateField("phoneNumber", event.target.value)}
                required
              />
              {fieldErrors.phoneNumber ? <small className="field-error">{fieldErrors.phoneNumber}</small> : null}
            </label>
            <label className="field field-wide">
              <span>Email</span>
              <input
                className={fieldErrors.email ? "input-error" : ""}
                type="email"
                value={form.email}
                onChange={(event) => updateField("email", event.target.value)}
                required
              />
              {fieldErrors.email ? <small className="field-error">{fieldErrors.email}</small> : null}
            </label>
          </div>
        </fieldset>

        <fieldset className="form-section">
          <legend>Address</legend>
          <div className="form-grid">
            <label className="field">
              <span>Province/city</span>
              <select
                className={fieldErrors.deliveryProvince ? "input-error" : ""}
                value={form.deliveryProvince}
                onChange={(event) => updateField("deliveryProvince", event.target.value as DeliveryInfoPayload["deliveryProvince"])}
                required
              >
                <option value="">Select a province/city</option>
                {VIETNAM_PROVINCES.map((province) => (
                  <option key={province} value={province}>
                    {province}
                  </option>
                ))}
              </select>
              {fieldErrors.deliveryProvince ? <small className="field-error">{fieldErrors.deliveryProvince}</small> : null}
            </label>
            <label className="field">
              <span>Delivery method</span>
              <select
                value={form.deliveryMethod}
                onChange={(event) => updateField("deliveryMethod", event.target.value as DeliveryInfoPayload["deliveryMethod"])}
              >
                <option value="STANDARD">Standard</option>
                <option value="EXPRESS">Express</option>
              </select>
            </label>
            <label className="field field-wide">
              <span>Detailed address</span>
              <input
                className={fieldErrors.deliveryAddress ? "input-error" : ""}
                value={form.deliveryAddress}
                onChange={(event) => updateField("deliveryAddress", event.target.value)}
                required
              />
              {fieldErrors.deliveryAddress ? <small className="field-error">{fieldErrors.deliveryAddress}</small> : null}
            </label>
            <label className="field field-wide">
              <span>Delivery instructions</span>
              <textarea
                value={form.deliveryInstructions}
                onChange={(event) => updateField("deliveryInstructions", event.target.value)}
              />
            </label>
          </div>
        </fieldset>

        <div className="form-actions">
          <button type="submit" className="button button-primary" disabled={isSubmitting}>
            {isSubmitting ? "Calculating invoice..." : "Continue to Invoice"}
          </button>
        </div>
      </form>

      <section className="workspace-card checkout-grid">
        <div className="checkout-main">
          <h2>Cart Items</h2>
          {cartStatus ? <p className="rule-note">{cartStatus}</p> : null}
          {cart && cart.stockErrors.length > 0 ? (
            <div className="alert alert-error">
              Some cart items exceed current stock. Go back to cart and update them before continuing.
            </div>
          ) : null}
          {cart && cart.items.length > 0 ? (
            <div className="table-shell">
              <table>
                <thead>
                  <tr>
                    <th>Product</th>
                    <th>Unit price</th>
                    <th>Quantity</th>
                    <th>Subtotal</th>
                  </tr>
                </thead>
                <tbody>
                  {cart.items.map((item) => (
                    <tr key={item.cartItemId}>
                      <td>
                        <strong>{item.productTitle}</strong>
                        <span className="table-subtext">{item.productType}</span>
                        {item.stockWarning ? (
                          <span className="field-error">{stockErrorMessage({ ...item.stockWarning, productTitle: item.productTitle })}</span>
                        ) : null}
                      </td>
                      <td>{money(item.unitPrice)}</td>
                      <td>{item.quantity}</td>
                      <td>{money(item.lineSubtotal)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>

        <aside className="summary-panel">
          <h2>Cart Summary</h2>
          <div className="summary-row">
            <span>Items</span>
            <span>{cart?.totalItems ?? 0}</span>
          </div>
          <div className="summary-row">
            <span>Subtotal (excl. VAT)</span>
            <span>{money(cart?.subtotalExclVat)}</span>
          </div>
          <Link className="button button-secondary full-width" href="/cart">
            Back to Cart to Edit Items
          </Link>
        </aside>
      </section>

      <aside className="workspace-card summary-panel" aria-label="Order summary">
        <h2>Order Summary</h2>
        {preview ? (
          <>
            <div className="summary-row">
              <span>Subtotal (excl. VAT)</span>
              <span>{money(preview.subtotalExclVat)}</span>
            </div>
            <div className="summary-row">
              <span>VAT (10%)</span>
              <span>{money(preview.vatAmount)}</span>
            </div>
            <div className="summary-row">
              <span>Delivery fee</span>
              <span>{money(preview.deliveryFee)}</span>
            </div>
            <div className="summary-row summary-total">
              <span>Estimated total</span>
              <span>{money(preview.totalAmountToPay)}</span>
            </div>
          </>
        ) : (
          <p className="lead">Enter a province/city to see the delivery fee and total.</p>
        )}
      </aside>
    </main>
  );
}
