"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ProductForm } from "@/features/products/components/ProductForm";
import { getProduct, updateProduct } from "@/features/products/api";
import type { Product, ProductPayload } from "@/features/products/types";

export default function EditProductPage() {
  const params = useParams();
  const router = useRouter();
  const productId = String(params.id);
  const [product, setProduct] = useState<Product | null>(null);
  const [status, setStatus] = useState("Loading product...");

  useEffect(() => {
    async function loadProduct() {
      try {
        setProduct(await getProduct(productId));
        setStatus("");
      } catch (error) {
        setStatus(error instanceof Error ? error.message : "Could not load product.");
      }
    }

    void loadProduct();
  }, [productId]);

  async function handleSubmit(payload: ProductPayload) {
    await updateProduct(productId, payload);
    router.push("/manager/products");
    // Bust the App Router cache so the list refetches the just-saved product
    // instead of serving the stale segment it cached before the edit.
    router.refresh();
  }

  if (status) {
    return (
      <main className="manager-shell">
        <div className="workspace-card">
          <div className="alert">{status}</div>
        </div>
      </main>
    );
  }

  if (!product) {
    return null;
  }

  return (
    <main className="manager-shell">
      <ProductForm mode="edit" initialProduct={product} onSubmit={handleSubmit} />
    </main>
  );
}
