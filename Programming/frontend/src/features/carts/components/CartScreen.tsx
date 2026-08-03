"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { createDraftOrder } from "@/features/orders/api";
import { saveOrderToken } from "@/lib/checkoutStorage";
import { ApiError } from "@/lib/apiClient";

import { CartItemRow } from "./CartItemRow";
import { getCart, removeCartItem, updateCartItem } from "../api";
import type { Cart, CartStockError } from "../types";

function formatCurrency(value: string | number) {
  return `${Number(value).toLocaleString()} VND`;
}

function stockErrorMessage(error: CartStockError) {
  return `${error.productTitle ?? "This item"} only has ${error.availableQuantity ?? 0} unit(s) available; reduce ${error.missingQuantity ?? 0} unit(s) before checkout.`;
}

export function CartScreen() {
  /*
   * Coupling/Cohesion: renders cart state and delegates all cart/order
   * mutations to feature API modules; it does not calculate stock or invoice rules.
   */
  const router = useRouter();
  const [cart, setCart] = useState<Cart | null>(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [busyItemId, setBusyItemId] = useState<string | null>(null);
  const [isPlacingOrder, setIsPlacingOrder] = useState(false);

  useEffect(() => {
    let active = true;
    getCart()
      .then((data) => {
        if (active) {
          setCart(data);
        }
      })
      .catch((loadError) => {
        if (active) {
          setError(loadError instanceof Error ? loadError.message : "Could not load cart.");
        }
      })
      .finally(() => {
        if (active) {
          setIsLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  async function handleQuantityChange(cartItemId: string, quantity: number) {
    if (quantity < 1) {
      return;
    }
    setBusyItemId(cartItemId);
    setError("");
    try {
      setCart(await updateCartItem(cartItemId, quantity));
    } catch (updateError) {
      setError(updateError instanceof Error ? updateError.message : "Could not update item.");
    } finally {
      setBusyItemId(null);
    }
  }

  async function handleRemove(cartItemId: string) {
    if (!window.confirm("Remove this item from your cart?")) {
      return;
    }
    setBusyItemId(cartItemId);
    setError("");
    try {
      setCart(await removeCartItem(cartItemId));
    } catch (removeError) {
      setError(removeError instanceof Error ? removeError.message : "Could not remove item.");
    } finally {
      setBusyItemId(null);
    }
  }

  async function handlePlaceOrder() {
    setIsPlacingOrder(true);
    setError("");
    try {
      const order = await createDraftOrder();
      window.localStorage.setItem("aims-current-order-id", order.orderId);
      saveOrderToken(order.orderToken);
      router.push("/checkout/delivery");
    } catch (placeOrderError) {
      if (placeOrderError instanceof ApiError) {
        const payload = placeOrderError.body as { cart?: CartStockError[] } | null;
        if (Array.isArray(payload?.cart) && payload.cart.length > 0) {
          setError(
            `Stock changed before checkout. Update your cart and try again: ${payload.cart.map(stockErrorMessage).join(" ")}`
          );
        } else {
          setError(placeOrderError.message);
        }
      } else {
        setError(placeOrderError instanceof Error ? placeOrderError.message : "Could not place order.");
      }
    } finally {
      setIsPlacingOrder(false);
    }
  }

  const hasItems = Boolean(cart && cart.items.length > 0);

  return (
    <main className="manager-shell">
      {/*
        SOLID Review
        Principle: SRP
        Reason: CartScreen loads cart state, updates/removes items, starts draft order creation, persists checkout tokens, and controls navigation.
        Impact: Cart UI, cart mutation, and order-placement workflow changes can force changes in one component and make behavior harder to test.
        Improvement: Move cart commands and order-start orchestration into hooks while keeping this component focused on rendering cart state.
      */}
      <header className="workspace-header">
        <div>
          <p className="eyebrow">AIMS Customer</p>
          <h1>Cart</h1>
          <p className="lead">Review selected products before entering delivery information.</p>
        </div>
        <Link className="button button-secondary" href="/">
          Continue Shopping
        </Link>
      </header>

      {error ? <div className="alert alert-error">{error}</div> : null}
      {cart && cart.stockErrors.length > 0 ? (
        <div className="alert alert-error">
          Some items exceed current stock. Review the affected quantities before checkout.
        </div>
      ) : null}

      <section className="workspace-card checkout-grid">
        <div className="checkout-main">
          {isLoading ? <p className="rule-note">Loading cart...</p> : null}
          {!isLoading && !hasItems ? <p className="empty-cell">Your cart is empty.</p> : null}
          {hasItems ? (
            <div className="table-shell">
              <table>
                <thead>
                  <tr>
                    <th>Product</th>
                    <th>Unit price</th>
                    <th>Quantity</th>
                    <th>Subtotal</th>
                    <th>Stock</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {cart?.items.map((item) => (
                    <CartItemRow
                      key={item.cartItemId}
                      item={item}
                      isBusy={busyItemId === item.cartItemId}
                      onQuantityChange={handleQuantityChange}
                      onRemove={handleRemove}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>

        <aside className="summary-panel">
          <h2>Order summary</h2>
          <div className="summary-row">
            <span>Items</span>
            <strong>{cart?.totalItems ?? 0}</strong>
          </div>
          <div className="summary-row">
            <span>Subtotal excluding VAT</span>
            <strong>{formatCurrency(cart?.subtotalExclVat ?? 0)}</strong>
          </div>
          <button
            type="button"
            className="button button-primary full-width"
            disabled={!hasItems || isPlacingOrder}
            onClick={handlePlaceOrder}
          >
            {isPlacingOrder ? "Checking stock..." : "Place Order"}
          </button>
        </aside>
      </section>
    </main>
  );
}
