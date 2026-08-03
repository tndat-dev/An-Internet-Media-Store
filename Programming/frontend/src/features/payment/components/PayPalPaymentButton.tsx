"use client";

import { useEffect, useRef, useState } from "react";
import { capturePayPalPayment, initiatePayPalPayment } from "../services/paymentApi";

type PayPalButtonOptions = {
  createOrder: () => Promise<string>;
  onApprove: (data: { orderID: string }) => Promise<void>;
  onCancel?: () => void;
  onError?: (error: unknown) => void;
  style?: Record<string, unknown>;
};

type PayPalSdk = {
  Buttons: (options: PayPalButtonOptions) => { render: (selector: string) => Promise<void> };
};

declare global {
  interface Window {
    paypal?: PayPalSdk;
  }
}

interface PayPalPaymentButtonProps {
  orderId: string;
  currency?: string;
  description?: string;
  returnUrl: string;
  cancelUrl: string;
  onError?: (message: string) => void;
}

export function PayPalPaymentButton({
  orderId,
  currency = "USD",
  description = "",
  returnUrl,
  cancelUrl,
  onError,
}: PayPalPaymentButtonProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const clientId = process.env.NEXT_PUBLIC_PAYPAL_CLIENT_ID;

  useEffect(() => {
    if (!clientId) {
      setError("Missing NEXT_PUBLIC_PAYPAL_CLIENT_ID in frontend/.env");
      return;
    }

    const existingScript = document.querySelector<HTMLScriptElement>('script[data-paypal-sdk="true"]');
    const initializeButtons = () => {
      if (!containerRef.current || !window.paypal) {
        return;
      }

      containerRef.current.innerHTML = "";

      window.paypal
        .Buttons({
          style: {
            layout: "vertical",
            color: "gold",
            shape: "rect",
            label: "paypal",
            tagline: false,
          },
          createOrder: async () => {
            const response = await initiatePayPalPayment({
              order_id: orderId,
              description,
              return_url: returnUrl,
              cancel_url: cancelUrl,
            });

            return response.provider_order_id;
          },
          onApprove: async ({ orderID }) => {
            const result = await capturePayPalPayment({
              provider_order_id: orderID,
              internal_order_id: orderId,
            });

            const transactionId = result.transaction_id ?? (result.id !== undefined ? String(result.id) : "");
            const successUrl = new URL("/checkout/success", window.location.origin);
            if (transactionId) {
              successUrl.searchParams.set("transactionId", transactionId);
            }
            if (result.captured_amount !== undefined || result.amount) {
              successUrl.searchParams.set("captured_amount", String(result.captured_amount ?? result.amount));
            }
            if (result.captured_currency || result.currency) {
              successUrl.searchParams.set("captured_currency", result.captured_currency ?? result.currency ?? "");
            }
            if (result.order_total_vnd || result.amount) {
              successUrl.searchParams.set("order_total_vnd", result.order_total_vnd ?? result.amount ?? "");
            }
            if (result.customer_name) {
              successUrl.searchParams.set("customer_name", result.customer_name);
            }
            if (result.phone_number) {
              successUrl.searchParams.set("phone_number", result.phone_number);
            }
            if (result.shipping_address) {
              successUrl.searchParams.set("shipping_address", result.shipping_address);
            }
            if (result.delivery_province) {
              successUrl.searchParams.set("delivery_province", result.delivery_province);
            }
            window.location.href = successUrl.toString();
          },
          onCancel: () => {
            window.location.href = cancelUrl;
          },
          onError: (err) => {
            const message = err instanceof Error ? err.message : "PayPal button error";
            setError(message);
            onError?.(message);
          },
        })
        .render("#paypal-button-container")
        .catch((err) => {
          const message = err instanceof Error ? err.message : "Unable to render PayPal buttons";
          setError(message);
          onError?.(message);
        });
    };

    if (existingScript) {
      if (window.paypal) {
        initializeButtons();
      } else {
        existingScript.addEventListener("load", initializeButtons, { once: true });
      }
      return;
    }

    const script = document.createElement("script");
    script.src = `https://www.paypal.com/sdk/js?client-id=${encodeURIComponent(clientId)}&currency=${encodeURIComponent(currency)}&intent=capture&components=buttons`;
    script.async = true;
    script.dataset.paypalSdk = "true";
    script.onload = initializeButtons;
    script.onerror = () => {
      const message = "Failed to load the PayPal JS SDK";
      setError(message);
      onError?.(message);
    };
    document.body.appendChild(script);

    return () => {
      script.onload = null;
    };
  }, [cancelUrl, clientId, currency, description, onError, orderId, returnUrl]);

  const handleFallbackRedirect = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await initiatePayPalPayment({
        order_id: orderId,
        description,
        return_url: returnUrl,
        cancel_url: cancelUrl,
      });

      window.location.href = response.approval_url;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Payment initiation failed.";
      setError(message);
      onError?.(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="paypal-button-panel">
      {/*
        SOLID Review
        Principle: SRP/DIP
        Reason: PayPalPaymentButton loads the PayPal SDK script, creates/captures backend payments, handles redirects, and renders fallback UI.
        Impact: The component is tightly coupled to the PayPal global SDK and backend API functions, making UI tests and provider replacement harder.
        Improvement: Extract SDK loading and payment orchestration into hooks/services and inject a payment client into the component.
      */}
      <div className="paypal-sdk-box">
        <div className="paypal-sdk-header">
          <p>PayPal Sandbox</p>
          <span>{clientId ? "Client ID loaded" : "Client ID missing"}</span>
        </div>
        <div id="paypal-button-container" ref={containerRef} />
        {!clientId && (
          <button
            type="button"
            onClick={handleFallbackRedirect}
            disabled={loading}
            className="button button-primary full-width"
          >
            {loading ? "Preparing PayPal..." : "Fallback: Pay with PayPal"}
          </button>
        )}
      </div>

      {error && (
        <p className="alert alert-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
