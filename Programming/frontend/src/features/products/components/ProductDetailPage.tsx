"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { addCartItem } from "@/features/carts/api";
import { parseApiError } from "@/lib/apiClient";

import { getCustomerProduct } from "../api";
import type { CustomerProduct } from "../types";
import { ProductDetailContent } from "./ProductDetailContent";

const CART_REASON_TEXT: Record<string, string> = {
  INSUFFICIENT_STOCK: "Not enough stock available.",
  PRODUCT_UNAVAILABLE: "This product is unavailable.",
  INVALID_QUANTITY: "Quantity must be greater than 0.",
};

type ProductDetailPageProps = {
  productId: string;
};

export function ProductDetailPage({ productId }: ProductDetailPageProps) {
  const [product, setProduct] = useState<CustomerProduct | null>(null);
  const [status, setStatus] = useState("Loading product detail...");
  const [quantity, setQuantity] = useState(1);
  const [busy, setBusy] = useState(false);
  const [cartMessage, setCartMessage] = useState<{ text: string; error: boolean } | null>(null);

  useEffect(() => {
    let isCurrent = true;

    async function loadProduct() {
      try {
        setStatus("Loading product detail...");
        const nextProduct = await getCustomerProduct(productId);
        if (isCurrent) {
          setProduct(nextProduct);
          setQuantity(1);
          setStatus("");
        }
      } catch (error) {
        if (isCurrent) {
          setStatus(error instanceof Error ? error.message : "Could not load product detail.");
        }
      }
    }

    void loadProduct();

    return () => {
      isCurrent = false;
    };
  }, [productId]);

  async function handleAddToCart() {
    if (!product) {
      return;
    }
    setCartMessage(null);
    setBusy(true);
    try {
      await addCartItem(product.product_id, quantity);
      setCartMessage({ text: "Added to cart.", error: false });
    } catch (error) {
      const fields = parseApiError(error);
      const reason = fields.quantity ?? "";
      setCartMessage({
        text: CART_REASON_TEXT[reason] ?? fields.detail ?? "Could not add to cart.",
        error: true,
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="product-detail-page">
      <div className="product-detail-toolbar">
        <Link className="button button-secondary" href="/">
          Back to catalog
        </Link>
        <Link className="button button-secondary" href="/cart">
          Cart
        </Link>
      </div>
      {cartMessage ? <div className={cartMessage.error ? "alert alert-error" : "alert"}>{cartMessage.text}</div> : null}
      {status ? <div className="alert">{status}</div> : null}
      {product ? (
        <section className="product-detail-page-panel" aria-label="Product detail">
          <ProductDetailContent
            product={product}
            quantity={quantity}
            busy={busy}
            onDecreaseQuantity={() => setQuantity((current) => Math.max(1, current - 1))}
            onIncreaseQuantity={() => setQuantity((current) => current + 1)}
            onAddToCart={handleAddToCart}
          />
        </section>
      ) : null}
    </main>
  );
}
