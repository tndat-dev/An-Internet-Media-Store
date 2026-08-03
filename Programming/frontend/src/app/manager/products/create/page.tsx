"use client";

import { useRouter } from "next/navigation";

import { ProductForm } from "@/features/products/components/ProductForm";
import { createProduct } from "@/features/products/api";
import type { ProductPayload } from "@/features/products/types";

export default function CreateProductPage() {
  const router = useRouter();

  async function handleSubmit(payload: ProductPayload) {
    await createProduct(payload);
    router.push("/manager/products");
    // Bust the App Router cache so the list refetches and includes the new product.
    router.refresh();
  }

  return (
    <main className="manager-shell">
      <ProductForm mode="create" onSubmit={handleSubmit} />
    </main>
  );
}
