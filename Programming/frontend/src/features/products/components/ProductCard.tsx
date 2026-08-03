"use client";

import Link from "next/link";
import { useState } from "react";

import type { CustomerProduct } from "../types";
import { ProductDetailPopup } from "./ProductDetailPopup";

type ProductCardProps = {
  product: CustomerProduct;
  onAddToCart: (productId: string, quantity: number) => Promise<void>;
};

function formatPrice(price: string) {
  return `${Number(price).toLocaleString()} VND`;
}

/**
 * Component: ProductCard
 *
 * Coupling/Cohesion level:
 * - Stamp Coupling with CustomerProduct because it renders a product card from the customer DTO.
 * - Data Coupling with ProductListScreen through the onView callback.
 * - Communicational Cohesion because the component renders one product card from one product record.
 *
 * Reason why:
 * The card keeps browsing presentation separate from list filtering and detail-popup fetching.
 */
export function ProductCard({ product, onAddToCart }: ProductCardProps) {
  const disabled = product.status !== "ACTIVE";
  const [busy, setBusy] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);

  async function handleAdd() {
    setBusy(true);
    try {
      await onAddToCart(product.product_id, 1);
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="product-card" onMouseLeave={() => setPreviewOpen(false)}>
      <div className="product-image-shell" onMouseEnter={() => setPreviewOpen(true)} onFocus={() => setPreviewOpen(true)}>
        {product.image_url ? (
          <div
            aria-label={product.title}
            className="product-image"
            role="img"
            style={{ backgroundImage: `url(${product.image_url})` }}
          />
        ) : (
          <div className="product-image-placeholder">{product.product_type}</div>
        )}
      </div>
      <div className="product-card-body">
        <p className="product-type">{product.product_type}</p>
        <h2 title={product.title} onMouseEnter={() => setPreviewOpen(true)} onFocus={() => setPreviewOpen(true)} tabIndex={0}>
          {product.title}
        </h2>
        <p className="product-price">{formatPrice(product.price)}</p>
        <div className="product-actions">
          <button className="button button-primary" disabled={disabled || busy} type="button" onClick={handleAdd}>
            {busy ? "Adding..." : "Add to Cart"}
          </button>
          <Link
            aria-label={`View details for ${product.title}`}
            className="button button-icon product-view-link"
            href={`/products/${product.product_id}`}
          >
            View
          </Link>
        </div>
      </div>
      {previewOpen ? <ProductDetailPopup productId={product.product_id} /> : null}
    </article>
  );
}
