"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { listProductHistory } from "@/features/products/api";
import type { ProductHistoryEntry } from "@/features/products/types";

const ACTION_LABELS: Record<string, string> = {
  CREATE: "Created",
  UPDATE: "Updated",
  DELETE: "Deleted",
  DEACTIVATE: "Deactivated",
  STOCK_ADJUST: "Stock adjusted",
};

function formatValue(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  return String(value);
}

// Compact before→after diff for the fields captured in ProductService.snapshot.
function summarizeChanges(changes: ProductHistoryEntry["changes"]): string[] {
  const before = changes?.before ?? {};
  const after = changes?.after ?? {};
  const keys = new Set([...Object.keys(before), ...Object.keys(after)]);
  const diffs: string[] = [];
  for (const key of keys) {
    if (key === "product_id") {
      continue;
    }
    const previous = before[key];
    const next = after[key];
    if (JSON.stringify(previous) === JSON.stringify(next)) {
      continue;
    }
    if (previous === undefined) {
      diffs.push(`${key}: ${formatValue(next)}`);
    } else if (next === undefined) {
      diffs.push(`${key}: ${formatValue(previous)} (removed)`);
    } else {
      diffs.push(`${key}: ${formatValue(previous)} → ${formatValue(next)}`);
    }
  }
  return diffs;
}

function ProductHistoryView() {
  const searchParams = useSearchParams();
  const productId = searchParams.get("product_id") ?? "";

  const [entries, setEntries] = useState<ProductHistoryEntry[]>([]);
  const [status, setStatus] = useState("Loading history...");
  const [actionFilter, setActionFilter] = useState("");

  useEffect(() => {
    let isCurrent = true;

    async function loadHistory() {
      setStatus("Loading history...");
      try {
        const data = await listProductHistory(productId || undefined);
        if (isCurrent) {
          setEntries(data);
          setStatus("");
        }
      } catch (error) {
        if (isCurrent) {
          setStatus(error instanceof Error ? error.message : "Could not load history.");
        }
      }
    }

    void loadHistory();
    return () => {
      isCurrent = false;
    };
  }, [productId]);

  const visibleEntries = useMemo(
    () => (actionFilter ? entries.filter((entry) => entry.action_type === actionFilter) : entries),
    [entries, actionFilter],
  );

  const productLabel = productId && entries.length > 0 ? entries[0].product_title : "";

  return (
    <main className="manager-shell">
      <header className="workspace-header">
        <div>
          <p className="eyebrow">AIMS Manager</p>
          <h1>Product history</h1>
          <p className="lead">
            {productId
              ? `Audit trail for ${productLabel || "this product"}.`
              : "Audit trail of product create, edit, and delete actions."}
          </p>
        </div>
        <Link className="button button-secondary" href="/manager/products">
          Back to products
        </Link>
      </header>

      <section className="workspace-card">
        <div className="toolbar">
          <label className="field compact-field">
            <span>Action</span>
            <select value={actionFilter} onChange={(event) => setActionFilter(event.target.value)}>
              <option value="">All actions</option>
              {Object.entries(ACTION_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          {productId ? (
            <Link className="button button-secondary" href="/manager/products/history">
              Show all products
            </Link>
          ) : null}
        </div>

        {status ? <div className="alert">{status}</div> : null}

        {!status ? (
          <div className="table-shell">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Product</th>
                  <th>Action</th>
                  <th>By</th>
                  <th>Reason</th>
                  <th>Changes</th>
                </tr>
              </thead>
              <tbody>
                {visibleEntries.map((entry) => {
                  const diffs = summarizeChanges(entry.changes);
                  return (
                    <tr key={entry.history_id}>
                      <td>{new Date(entry.created_at).toLocaleString()}</td>
                      <td>{entry.product_title}</td>
                      <td>
                        <span className="status-pill history-action">
                          {ACTION_LABELS[entry.action_type] ?? entry.action_type}
                        </span>
                      </td>
                      <td>{entry.performed_by ?? "—"}</td>
                      <td>{entry.reason || "—"}</td>
                      <td>
                        {diffs.length > 0 ? (
                          <ul className="history-changes">
                            {diffs.map((diff) => (
                              <li key={diff}>{diff}</li>
                            ))}
                          </ul>
                        ) : (
                          "—"
                        )}
                      </td>
                    </tr>
                  );
                })}
                {visibleEntries.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="empty-cell">
                      No history records found.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </main>
  );
}

export default function ProductHistoryPage() {
  return (
    <Suspense
      fallback={
        <main className="manager-shell">
          <div className="workspace-card">
            <div className="alert">Loading history...</div>
          </div>
        </main>
      }
    >
      <ProductHistoryView />
    </Suspense>
  );
}
