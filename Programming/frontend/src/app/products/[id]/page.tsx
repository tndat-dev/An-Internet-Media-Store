"use client";

import { useParams } from "next/navigation";

import { ProductDetailPage } from "@/features/products/components/ProductDetailPage";

export default function CustomerProductDetailRoute() {
  const params = useParams();
  return <ProductDetailPage productId={String(params.id)} />;
}
