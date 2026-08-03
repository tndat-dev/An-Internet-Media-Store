/*
 * SOLID Review
 * Principle: SRP/OCP
 * Reason: products/api.ts contains both manager CUD endpoints and customer read/detail endpoints in one module.
 * Impact: Manager product changes and customer catalog changes can force edits in the same API boundary and make imports less focused.
 * Improvement: Split manager product command APIs from customer product query APIs while sharing DTO types.
 */
import { apiClient } from "@/lib/apiClient";

import type {
  CustomerProduct,
  CustomerProductFilters,
  Paginated,
  Product,
  ProductHistoryEntry,
  ProductPayload,
} from "./types";

function toQueryString(params: Record<string, string | undefined>) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) {
      query.set(key, value);
    }
  }
  const queryString = query.toString();
  return queryString ? `?${queryString}` : "";
}

export function listProducts(search = "") {
  const query = search ? `?search=${encodeURIComponent(search)}` : "";
  return apiClient<Product[]>(`/products/${query}`);
}

export function getProduct(productId: string) {
  return apiClient<Product>(`/products/${productId}/`);
}

// Manager identity now comes from the auth token (attached by apiClient); the
// backend requires a PRODUCT_MANAGER token for these writes.
export function createProduct(payload: ProductPayload) {
  return apiClient<Product>("/products/", {
    method: "POST",
    body: payload,
  });
}

export function updateProduct(productId: string, payload: Partial<ProductPayload>) {
  return apiClient<Product>(`/products/${productId}/`, {
    method: "PATCH",
    body: payload,
  });
}

export function deleteProducts(productIds: string[]) {
  return apiClient<Product[]>("/products/delete/", {
    method: "POST",
    body: { product_ids: productIds },
  });
}

// Product CUD audit trail (Problem Statement: managers can query histories).
// Backed by ProductHistoryListView; optionally filtered to one product.
export function listProductHistory(productId?: string) {
  const query = productId ? `?product_id=${encodeURIComponent(productId)}` : "";
  return apiClient<ProductHistoryEntry[]>(`/products/histories/${query}`);
}

/**
 * Coupling/Cohesion level:
 * - Coupling: Data coupling with ProductListScreen through explicit customer filter values.
 * - Cohesion: Functional cohesion.
 *
 * Reason why: The function only maps customer product-list UI filters to the public read endpoint.
 */
export function listCustomerProducts(filters: CustomerProductFilters = {}, page = 1) {
  const query = toQueryString({
    scope: "customer",
    search: filters.search,
    category: filters.category,
    min_price: filters.minPrice,
    max_price: filters.maxPrice,
    sort: filters.sort,
    page: page > 1 ? String(page) : undefined,
  });
  return apiClient<Paginated<CustomerProduct>>(`/products/${query}`);
}

/**
 * Coupling/Cohesion level:
 * - Coupling: Data coupling with ProductDetailPopup through productId.
 * - Cohesion: Functional cohesion.
 *
 * Reason why: The function only fetches one customer-visible product detail DTO.
 */
export function getCustomerProduct(productId: string) {
  return apiClient<CustomerProduct>(`/products/${productId}/?scope=customer`);
}
