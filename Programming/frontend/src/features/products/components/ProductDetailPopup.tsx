"use client";

import { useEffect, useState } from "react";

import { getCustomerProduct } from "../api";
import type { CustomerProduct } from "../types";
import { ProductDetailContent } from "./ProductDetailContent";

type ProductDetailPopupProps = {
  productId: string | null;
};

/**
 * Component: ProductDetailPopup
 *
 * Coupling/Cohesion level:
 * - Data Coupling with products API through productId.
 * - Stamp Coupling with CustomerProduct because it renders the customer detail DTO.
 * - Procedural Cohesion because it coordinates fetch, loading/error state, and modal rendering for one detail interaction.
 *
 * Reason why:
 * The popup owns the customer detail workflow and delegates type-specific fields to smaller functional components.
 */
export function ProductDetailPopup({ productId }: ProductDetailPopupProps) {
  const [product, setProduct] = useState<CustomerProduct | null>(null);
  const [status, setStatus] = useState("");

  useEffect(() => {
    if (!productId) {
      return;
    }

    let isCurrent = true;

    async function loadProductDetail() {
      try {
        setStatus("Loading product detail...");
        const nextProduct = await getCustomerProduct(productId as string);
        if (isCurrent) {
          setProduct(nextProduct);
          setStatus("");
        }
      } catch (error) {
        if (isCurrent) {
          setStatus(error instanceof Error ? error.message : "Product detail could not be loaded.");
        }
      }
    }

    void loadProductDetail();

    return () => {
      isCurrent = false;
    };
  }, [productId]);

  if (!productId) {
    return null;
  }

  const visibleProduct = product?.product_id === productId ? product : null;

  return (
    <section className="product-hover-preview" aria-label="Product detail preview">
      {status ? <div className="alert">{status}</div> : null}
      {visibleProduct ? <ProductDetailContent product={visibleProduct} variant="preview" /> : null}
    </section>
  );
}
