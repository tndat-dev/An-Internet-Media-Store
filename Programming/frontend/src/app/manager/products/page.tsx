"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { ProductDeleteDialog } from "@/features/products/components/ProductDeleteDialog";
import { ProductTable } from "@/features/products/components/ProductTable";
import { deleteProducts, listProducts } from "@/features/products/api";
import type { Product } from "@/features/products/types";
import { LOW_STOCK_THRESHOLD, MAX_DELETE_PER_REQUEST } from "@/lib/constants";

export default function ManagerProductsPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [selectedProductIds, setSelectedProductIds] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("Loading products...");
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  async function loadProducts(query = "") {
    setStatus("Loading products...");
    try {
      const nextProducts = await listProducts(query);
      setProducts(nextProducts);
      setStatus("");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Could not load products.");
    }
  }

  useEffect(() => {
    let isCurrent = true;

    async function loadInitialProducts() {
      try {
        const nextProducts = await listProducts();
        if (isCurrent) {
          setProducts(nextProducts);
          setStatus("");
        }
      } catch (error) {
        if (isCurrent) {
          setStatus(error instanceof Error ? error.message : "Could not load products.");
        }
      }
    }

    void loadInitialProducts();

    return () => {
      isCurrent = false;
    };
  }, []);

  const selectedCount = selectedProductIds.length;
  const deleteLimitReached = selectedCount > MAX_DELETE_PER_REQUEST;

  const stockSummary = useMemo(() => {
    const active = products.filter((product) => product.status === "ACTIVE").length;
    const lowStock = products.filter(
      (product) => product.stock_quantity > 0 && product.stock_quantity <= LOW_STOCK_THRESHOLD,
    ).length;
    return { active, lowStock };
  }, [products]);

  function toggleProduct(productId: string) {
    setSelectedProductIds((current) =>
      current.includes(productId)
        ? current.filter((selectedId) => selectedId !== productId)
        : [...current, productId],
    );
  }

  function toggleAll() {
    setSelectedProductIds((current) =>
      current.length === products.length ? [] : products.map((product) => product.product_id),
    );
  }

  async function confirmDelete() {
    setIsDeleting(true);
    try {
      await deleteProducts(selectedProductIds);
      setSelectedProductIds([]);
      setIsDeleteOpen(false);
      await loadProducts(search);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Could not delete selected products.");
    } finally {
      setIsDeleting(false);
    }
  }

  return (
    <main className="manager-shell">
      <header className="workspace-header">
        <div>
          <p className="eyebrow">AIMS Manager</p>
          <h1>Products</h1>
          <p className="lead">Create, update, and delete products according to the Product Manager rules.</p>
        </div>
        <div className="header-actions">
          <Link className="button button-secondary" href="/manager/products/history">
            History
          </Link>
          <Link className="button button-primary" href="/manager/products/create">
            Create product
          </Link>
        </div>
      </header>

      <section className="metric-row" aria-label="Product summary">
        <div className="metric">
          <span>Total products</span>
          <strong>{products.length}</strong>
        </div>
        <div className="metric">
          <span>Active</span>
          <strong>{stockSummary.active}</strong>
        </div>
        <div className="metric">
          <span>Low stock</span>
          <strong>{stockSummary.lowStock}</strong>
        </div>
      </section>

      <section className="workspace-card">
        <div className="toolbar">
          <form
            className="search-form"
            onSubmit={(event) => {
              event.preventDefault();
              void loadProducts(search);
            }}
          >
            <label className="field compact-field">
              <span>Search</span>
              <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Product title" />
            </label>
            <button className="button button-secondary" type="submit">
              Search
            </button>
          </form>

          <button
            className="button button-danger"
            disabled={selectedCount === 0 || deleteLimitReached}
            type="button"
            onClick={() => setIsDeleteOpen(true)}
          >
            Delete selected
          </button>
        </div>

        {deleteLimitReached ? (
          <div className="alert alert-error">
            Select at most {MAX_DELETE_PER_REQUEST} products per delete request.
          </div>
        ) : null}
        {status ? <div className="alert">{status}</div> : null}

        <ProductTable
          products={products}
          selectedProductIds={selectedProductIds}
          onToggleProduct={toggleProduct}
          onToggleAll={toggleAll}
        />
      </section>

      <ProductDeleteDialog
        count={selectedCount}
        isOpen={isDeleteOpen}
        isDeleting={isDeleting}
        onCancel={() => setIsDeleteOpen(false)}
        onConfirm={confirmDelete}
      />
    </main>
  );
}
