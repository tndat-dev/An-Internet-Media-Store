"use client";

import { useEffect, useMemo, useState } from "react";

import { listProductHistory, listProducts } from "@/features/products/api";
import type { Product, ProductHistoryEntry, ProductType } from "@/features/products/types";
import { LOW_STOCK_THRESHOLD } from "@/lib/constants";
import { formatVND } from "@/lib/formatMoney";

const TYPE_LABELS: Record<ProductType, string> = {
  BOOK: "Books",
  CD: "CDs",
  DVD: "DVDs",
  NEWSPAPER: "Newspapers",
};

const ACTION_LABELS: Record<string, string> = {
  CREATE: "Created",
  UPDATE: "Updated",
  DELETE: "Deleted",
  DEACTIVATE: "Deactivated",
  STOCK_ADJUST: "Stock adjusted",
};

export default function ManagerAnalyticsPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [history, setHistory] = useState<ProductHistoryEntry[]>([]);
  const [status, setStatus] = useState("Loading analytics...");

  useEffect(() => {
    let isCurrent = true;

    async function load() {
      try {
        const [productList, historyList] = await Promise.all([listProducts(), listProductHistory()]);
        if (isCurrent) {
          setProducts(productList);
          setHistory(historyList);
          setStatus("");
        }
      } catch (error) {
        if (isCurrent) {
          setStatus(error instanceof Error ? error.message : "Could not load analytics.");
        }
      }
    }

    void load();
    return () => {
      isCurrent = false;
    };
  }, []);

  const stats = useMemo(() => {
    const byType: Record<ProductType, number> = { BOOK: 0, CD: 0, DVD: 0, NEWSPAPER: 0 };
    let active = 0;
    let outOfStock = 0;
    let deactivated = 0;
    let lowStock = 0;
    let units = 0;
    let inventoryValue = 0;

    for (const product of products) {
      byType[product.product_type] += 1;
      units += product.stock_quantity;
      inventoryValue += Number(product.current_price) * product.stock_quantity;

      if (product.status === "DEACTIVATED") {
        deactivated += 1;
      } else if (product.status === "ACTIVE") {
        if (product.stock_quantity === 0) {
          outOfStock += 1;
        } else {
          active += 1;
          if (product.stock_quantity <= LOW_STOCK_THRESHOLD) {
            lowStock += 1;
          }
        }
      }
    }

    return { total: products.length, active, outOfStock, deactivated, lowStock, units, inventoryValue, byType };
  }, [products]);

  const actionCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const entry of history) {
      counts[entry.action_type] = (counts[entry.action_type] ?? 0) + 1;
    }
    return counts;
  }, [history]);

  const recentActivity = history.slice(0, 8);

  return (
    <main className="manager-shell">
      <header className="workspace-header">
        <div>
          <p className="eyebrow">AIMS Manager</p>
          <h1>Analytics</h1>
          <p className="lead">Catalog, inventory, and recent product management activity at a glance.</p>
        </div>
      </header>

      {status ? <div className="alert">{status}</div> : null}

      {!status ? (
        <>
          <section className="metric-row" aria-label="Catalog summary">
            <div className="metric">
              <span>Total products</span>
              <strong>{stats.total}</strong>
            </div>
            <div className="metric">
              <span>Active</span>
              <strong>{stats.active}</strong>
            </div>
            <div className="metric">
              <span>Out of stock</span>
              <strong>{stats.outOfStock}</strong>
            </div>
            <div className="metric">
              <span>Low stock</span>
              <strong>{stats.lowStock}</strong>
            </div>
            <div className="metric">
              <span>Deactivated</span>
              <strong>{stats.deactivated}</strong>
            </div>
          </section>

          <section className="metric-row" aria-label="Inventory summary">
            <div className="metric">
              <span>Units in stock</span>
              <strong>{stats.units}</strong>
            </div>
            <div className="metric">
              <span>Inventory value (excl. VAT)</span>
              <strong>{formatVND(stats.inventoryValue)}</strong>
            </div>
          </section>

          <section className="workspace-card">
            <h2>Products by type</h2>
            <div className="table-shell">
              <table>
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Count</th>
                  </tr>
                </thead>
                <tbody>
                  {(Object.keys(TYPE_LABELS) as ProductType[]).map((type) => (
                    <tr key={type}>
                      <td>{TYPE_LABELS[type]}</td>
                      <td>{stats.byType[type]}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="workspace-card">
            <div className="workspace-header">
              <h2>Recent activity</h2>
              <div className="analytics-action-counts">
                {Object.entries(ACTION_LABELS).map(([action, label]) => (
                  <span key={action} className="status-pill history-action">
                    {label}: {actionCounts[action] ?? 0}
                  </span>
                ))}
              </div>
            </div>
            <div className="table-shell">
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Product</th>
                    <th>Action</th>
                    <th>By</th>
                  </tr>
                </thead>
                <tbody>
                  {recentActivity.map((entry) => (
                    <tr key={entry.history_id}>
                      <td>{new Date(entry.created_at).toLocaleString()}</td>
                      <td>{entry.product_title}</td>
                      <td>
                        <span className="status-pill history-action">
                          {ACTION_LABELS[entry.action_type] ?? entry.action_type}
                        </span>
                      </td>
                      <td>{entry.performed_by ?? "—"}</td>
                    </tr>
                  ))}
                  {recentActivity.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="empty-cell">
                        No activity recorded yet.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </section>
        </>
      ) : null}
    </main>
  );
}
