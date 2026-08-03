"use client";

import { useEffect, useMemo, useState } from "react";

import { addCartItem } from "@/features/carts/api";
import { parseApiError } from "@/lib/apiClient";

import { listCustomerProducts } from "../api";
import type { CustomerProduct, CustomerProductFilters } from "../types";
import { ProductCard } from "./ProductCard";

const categoryOptions = ["Book", "CD", "DVD", "Newspaper"];
const PRODUCTS_PER_PAGE = 20;

const CART_REASON_TEXT: Record<string, string> = {
  INSUFFICIENT_STOCK: "Not enough stock available.",
  PRODUCT_UNAVAILABLE: "This product is unavailable.",
  INVALID_QUANTITY: "Quantity must be greater than 0.",
};

/**
 * Component: ProductListScreen
 *
 * Coupling/Cohesion level:
 * - Data Coupling with products API through explicit filter fields.
 * - Stamp Coupling with CustomerProduct cards because it passes product DTOs to ProductCard.
 * - Procedural Cohesion because it coordinates customer browsing, filtering, loading state, and detail popup selection.
 *
 * Reason why:
 * This component owns the customer catalog workflow while delegating card and detail rendering to focused child components.
 */
export function ProductListScreen() {
  const [products, setProducts] = useState<CustomerProduct[]>([]);
  // Empty filters on first load => backend returns 20 random products (Problem Statement).
  const [filters, setFilters] = useState<CustomerProductFilters>({});
  const [draftFilters, setDraftFilters] = useState<CustomerProductFilters>({});
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [hasNext, setHasNext] = useState(false);
  const [hasPrev, setHasPrev] = useState(false);
  const [status, setStatus] = useState("Loading products...");
  const [cartMessage, setCartMessage] = useState<{ text: string; error: boolean } | null>(null);

  async function handleAddToCart(productId: string, quantity: number) {
    setCartMessage(null);
    try {
      await addCartItem(productId, quantity);
      setCartMessage({ text: "Added to cart.", error: false });
    } catch (error) {
      const fields = parseApiError(error);
      const reason = fields.quantity ?? "";
      setCartMessage({
        text: CART_REASON_TEXT[reason] ?? fields.detail ?? "Could not add to cart.",
        error: true,
      });
    }
  }

  useEffect(() => {
    let isCurrent = true;

    async function loadProducts() {
      try {
        const response = await listCustomerProducts(filters, page);
        if (isCurrent) {
          setProducts(response.results);
          setTotalCount(response.count);
          setHasNext(Boolean(response.next));
          setHasPrev(Boolean(response.previous));
          setStatus("");
        }
      } catch (error) {
        if (isCurrent) {
          setStatus(error instanceof Error ? error.message : "Could not load products.");
        }
      }
    }

    void loadProducts();

    return () => {
      isCurrent = false;
    };
  }, [filters, page]);

  const summary = useMemo(() => ({ total: totalCount }), [totalCount]);
  const totalPages = Math.max(1, Math.ceil(totalCount / PRODUCTS_PER_PAGE));
  const pageItems = useMemo(() => {
    const visiblePages = new Set([1, totalPages, page - 1, page, page + 1]);
    const items: Array<number | "ellipsis"> = [];
    let lastPage = 0;

    for (let pageNumber = 1; pageNumber <= totalPages; pageNumber += 1) {
      if (!visiblePages.has(pageNumber)) {
        continue;
      }
      if (lastPage && pageNumber - lastPage > 1) {
        items.push("ellipsis");
      }
      items.push(pageNumber);
      lastPage = pageNumber;
    }

    return items;
  }, [page, totalPages]);

  function submitFilters(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus("Loading products...");
    setPage(1); // new search/filter starts from the first page
    setFilters(draftFilters);
  }

  function goToPage(nextPage: number) {
    setStatus("Loading products...");
    setPage(nextPage);
    if (typeof window !== "undefined") {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  }

  function updateDraftFilter(key: keyof CustomerProductFilters, value: string) {
    setDraftFilters((current) => ({ ...current, [key]: value }));
  }

  return (
    <main className="catalog-page">
      {/*
        SOLID Review
        Principle: SRP
        Reason: ProductListScreen handles filters, pagination, product loading, add-to-cart API errors, and detail popup selection in one component.
        Impact: Catalog UI changes and cart workflow changes can collide, increasing maintenance and test complexity.
        Improvement: Extract catalog query state and cart-add behavior into dedicated hooks or container services.
      */}
      <section className="catalog-main">
        <header className="catalog-header">
          <div>
            <p className="eyebrow">AIMS Catalog</p>
            <h2>Product List</h2>
          </div>
          <p className="catalog-summary">
            {summary.total} product{summary.total === 1 ? "" : "s"} found
          </p>
        </header>

        <form className="catalog-filters" onSubmit={submitFilters}>
          <label>
            <span>Search</span>
            <input
              value={draftFilters.search ?? ""}
              placeholder="Search publications..."
              onChange={(event) => updateDraftFilter("search", event.target.value)}
            />
          </label>
          <label>
            <span>Category</span>
            <select
              value={draftFilters.category ?? ""}
              onChange={(event) => updateDraftFilter("category", event.target.value)}
            >
              <option value="">All Categories</option>
              {categoryOptions.map((category) => (
                <option key={category} value={category}>
                  {category}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Min Price</span>
            <input
              inputMode="numeric"
              value={draftFilters.minPrice ?? ""}
              placeholder="Min Price"
              onChange={(event) => updateDraftFilter("minPrice", event.target.value)}
            />
          </label>
          <label>
            <span>Max Price</span>
            <input
              inputMode="numeric"
              value={draftFilters.maxPrice ?? ""}
              placeholder="Max Price"
              onChange={(event) => updateDraftFilter("maxPrice", event.target.value)}
            />
          </label>
          <label>
            <span>Sort</span>
            <select
              value={draftFilters.sort ?? ""}
              onChange={(event) => updateDraftFilter("sort", event.target.value)}
            >
              <option value="">Featured</option>
              <option value="title">Sort by: Title</option>
              <option value="newest">Sort by: Newest</option>
              <option value="price_asc">Sort by: Price low to high</option>
              <option value="price_desc">Sort by: Price high to low</option>
            </select>
          </label>
          <button className="button button-primary" type="submit">
            Apply
          </button>
        </form>

        {cartMessage ? (
          <div className={cartMessage.error ? "alert alert-error" : "alert"}>{cartMessage.text}</div>
        ) : null}
        {status ? <div className="alert">{status}</div> : null}
        {!status && products.length === 0 ? <div className="empty-catalog">No products found.</div> : null}

        <div className="product-grid">
          {products.map((product) => (
            <ProductCard
              key={product.product_id}
              product={product}
              onAddToCart={handleAddToCart}
            />
          ))}
        </div>

        {totalPages > 1 ? (
          <nav className="catalog-pagination" aria-label="Product pages">
            <button
              type="button"
              className="pagination-button pagination-edge"
              disabled={!hasPrev}
              aria-label="First page"
              onClick={() => goToPage(1)}
            >
              First
            </button>
            <button
              type="button"
              className="pagination-button"
              disabled={!hasPrev}
              aria-label="Previous page"
              onClick={() => goToPage(page - 1)}
            >
              Prev
            </button>
            <div className="pagination-pages" aria-label={`Page ${page} of ${totalPages}`}>
              {pageItems.map((item, index) =>
                item === "ellipsis" ? (
                  <span key={`ellipsis-${index}`} className="pagination-ellipsis" aria-hidden="true">
                    ...
                  </span>
                ) : (
                  <button
                    key={item}
                    type="button"
                    className={item === page ? "pagination-button pagination-current" : "pagination-button"}
                    aria-current={item === page ? "page" : undefined}
                    onClick={() => goToPage(item)}
                  >
                    {item}
                  </button>
                ),
              )}
            </div>
            <button
              type="button"
              className="pagination-button"
              disabled={!hasNext}
              aria-label="Next page"
              onClick={() => goToPage(page + 1)}
            >
              Next
            </button>
            <button
              type="button"
              className="pagination-button pagination-edge"
              disabled={!hasNext}
              aria-label="Last page"
              onClick={() => goToPage(totalPages)}
            >
              Last
            </button>
            <span className="catalog-page-size">Showing {PRODUCTS_PER_PAGE} items/page</span>
          </nav>
        ) : null}
      </section>

    </main>
  );
}
