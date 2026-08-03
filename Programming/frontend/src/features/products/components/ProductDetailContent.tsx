"use client";

import type { CustomerProduct } from "../types";
import { BookDetail } from "./BookDetail";
import { CDDetail } from "./CDDetail";
import { DVDDetail } from "./DVDDetail";
import { NewspaperDetail } from "./NewspaperDetail";

type ProductDetailContentProps = {
  product: CustomerProduct;
  quantity?: number;
  busy?: boolean;
  variant?: "full" | "preview";
  onDecreaseQuantity?: () => void;
  onIncreaseQuantity?: () => void;
  onAddToCart?: () => Promise<void> | void;
};

function formatPrice(price: string) {
  return `${Number(price).toLocaleString()} VND`;
}

/**
 * Derives the "by ..." byline from the primary creator of each media type so the
 * detail header mirrors a storefront product page (e.g. "by Robert C. Martin").
 */
function getByline(product: CustomerProduct): string | null {
  switch (product.product_type) {
    case "BOOK":
      return product.type_details.authors ? `by ${product.type_details.authors}` : null;
    case "CD":
      return product.type_details.artists ? `by ${product.type_details.artists}` : null;
    case "DVD":
      return product.type_details.director ? `Directed by ${product.type_details.director}` : null;
    case "NEWSPAPER":
      return product.type_details.editor_in_chief ? `Edited by ${product.type_details.editor_in_chief}` : null;
  }
}

function getStatusBadge(product: CustomerProduct): { label: string; tone: "in" | "out" | "unavailable" } {
  if (product.status !== "ACTIVE") {
    return product.status === "DEACTIVATED"
      ? { label: "Unavailable", tone: "unavailable" }
      : { label: "Out of stock", tone: "unavailable" };
  }
  if (product.stock_quantity <= 0) {
    return { label: "Out of stock", tone: "out" };
  }
  return { label: "In stock", tone: "in" };
}

function hasValue(value: string | undefined): boolean {
  return Boolean(value) && Number(value) > 0;
}

/**
 * Renders the physical attributes captured by the Product Manager (dimensions,
 * weight, barcode) so the customer detail page mirrors the full product record.
 */
function PhysicalDetail({ product }: { product: CustomerProduct }) {
  const hasDimensions = hasValue(product.height) || hasValue(product.width) || hasValue(product.length);

  if (!hasDimensions && !hasValue(product.weight) && !product.barcode) {
    return null;
  }

  return (
    <dl className="detail-grid">
      <div>
        <dt>Dimensions </dt>
          <dt>(Height × Width × Length)</dt>
        <dd>{hasDimensions ? `${product.height} × ${product.width} × ${product.length} cm` : "Not specified"}</dd>
      </div>
      <div>
        <dt>Weight</dt>
        <dd>{hasValue(product.weight) ? `${product.weight} kg` : "Not specified"}</dd>
      </div>
      <div>
        <dt>Barcode</dt>
        <dd>{product.barcode || "Not specified"}</dd>
      </div>
    </dl>
  );
}

function TypeSpecificDetail({ product }: { product: CustomerProduct }) {
  switch (product.product_type) {
    case "BOOK":
      return <BookDetail details={product.type_details} />;
    case "CD":
      return <CDDetail details={product.type_details} />;
    case "DVD":
      return <DVDDetail details={product.type_details} />;
    case "NEWSPAPER":
      return <NewspaperDetail details={product.type_details} />;
  }
}

export function ProductDetailContent({
  product,
  quantity = 1,
  busy = false,
  variant = "full",
  onDecreaseQuantity,
  onIncreaseQuantity,
  onAddToCart,
}: ProductDetailContentProps) {
  const canPurchase = product.status === "ACTIVE" && Boolean(onAddToCart);
  const isFull = variant === "full";
  const byline = getByline(product);
  const statusBadge = getStatusBadge(product);

  return (
    <>
      <div className="detail-media">
        {product.image_url ? (
          <div
            aria-label={product.title}
            className="detail-image"
            role="img"
            style={{ backgroundImage: `url(${product.image_url})` }}
          />
        ) : (
          <div className="detail-image-placeholder">{product.product_type}</div>
        )}
      </div>
      <div className="detail-content">
        <div className="detail-heading-row">
          <span className="type-chip">{product.product_type}</span>
          <span className={`detail-status-badge tone-${statusBadge.tone}`}>{statusBadge.label}</span>
        </div>
        <h2>{product.title}</h2>
        {byline ? <p className="detail-byline">{byline}</p> : null}
        {product.category ? (
          <p className="detail-category">
            Category <span>{product.category}</span>
          </p>
        ) : null}
        <p className="detail-price">{formatPrice(product.price)}</p>
        {product.status !== "ACTIVE" ? (
          <p className="availability-note">
            {product.status === "DEACTIVATED" ? "This product is unavailable." : "This product is out of stock."}
          </p>
        ) : product.stock_quantity <= 0 ? (
          <p className="availability-note">
            This product is currently out of stock, but you can still add it to your cart and the system will re-check stock at checkout.
          </p>
        ) : null}
        <p className="detail-description">{product.description || "No description available."}</p>
        {isFull ? <h3 className="detail-spec-title">Specifications</h3> : null}
        <TypeSpecificDetail product={product} />
        {isFull ? <PhysicalDetail product={product} /> : null}
        {variant === "full" ? (
          canPurchase ? (
            <div className="detail-purchase">
              <div className="qty-stepper" aria-label="Quantity">
                <button
                  type="button"
                  className="button button-secondary"
                  onClick={onDecreaseQuantity}
                  disabled={quantity <= 1}
                  aria-label="Decrease quantity"
                >
                  -
                </button>
                <span className="qty-value">{quantity}</span>
                <button
                  type="button"
                  className="button button-secondary"
                  onClick={onIncreaseQuantity}
                  aria-label="Increase quantity"
                >
                  +
                </button>
              </div>
              <button className="button button-primary detail-cart-button" disabled={busy} type="button" onClick={onAddToCart}>
                {busy ? "Adding..." : "Add to Cart"}
              </button>
            </div>
          ) : (
            <button className="button button-primary detail-cart-button" disabled type="button">
              Add to Cart
            </button>
          )
        ) : null}
      </div>
    </>
  );
}
