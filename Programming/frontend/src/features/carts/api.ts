/*
 * SOLID Review
 * Principle: SRP/DIP
 * Reason: carts/api.ts manages cart token persistence, HTTP calls, and global cart-count event broadcasting in one module.
 * Impact: Storage, network, and UI synchronization changes are coupled, making the cart client harder to test or reuse.
 * Improvement: Extract cart token storage and event publishing behind small adapters used by the cart API client.
 */

/*
 * Coupling/Cohesion: owns HTTP integration for the cart feature only.
 * It is coupled to cart token handling and cart endpoints, while keeping
 * higher-level checkout flows in orders/api.ts.
 */
import { apiClient } from "@/lib/apiClient";

import type { Cart } from "./types";

const CART_TOKEN_STORAGE_KEY = "aims-cart-token";

function createFallbackToken() {
  return `cart-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function getCartToken() {
  if (typeof window === "undefined") {
    return "";
  }

  const existingToken = window.localStorage.getItem(CART_TOKEN_STORAGE_KEY);
  if (existingToken) {
    return existingToken;
  }

  const token = window.crypto?.randomUUID?.() ?? createFallbackToken();
  window.localStorage.setItem(CART_TOKEN_STORAGE_KEY, token);
  return token;
}

function cartHeaders() {
  return {
    "X-Cart-Token": getCartToken(),
  };
}

// Broadcasts the cart item count so the header badge stays in sync without a
// shared store. Components fetch/mutate via this module; the header just listens.
export const CART_UPDATED_EVENT = "aims:cart-updated";

function broadcastCartCount(cart: Cart) {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent<number>(CART_UPDATED_EVENT, { detail: cart.totalItems }));
  }
  return cart;
}

export function getCart() {
  return apiClient<Cart>("/cart/", {
    headers: cartHeaders(),
  }).then(broadcastCartCount);
}

export function addCartItem(productId: string, quantity: number) {
  return apiClient<Cart>("/cart/items/", {
    method: "POST",
    body: { productId, quantity },
    headers: cartHeaders(),
  }).then(broadcastCartCount);
}

export function updateCartItem(cartItemId: string, quantity: number) {
  return apiClient<Cart>(`/cart/items/${cartItemId}/`, {
    method: "PATCH",
    body: { quantity },
    headers: cartHeaders(),
  }).then(broadcastCartCount);
}

export function removeCartItem(cartItemId: string) {
  return apiClient<Cart>(`/cart/items/${cartItemId}/`, {
    method: "DELETE",
    headers: cartHeaders(),
  }).then(broadcastCartCount);
}
