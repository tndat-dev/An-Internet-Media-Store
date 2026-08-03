"use client";

import Link from "next/link";

import type { Product } from "@/features/products/types";
import { formatVND } from "@/lib/formatMoney";

type ProductTableProps = {
  products: Product[];
  selectedProductIds: string[];
  onToggleProduct: (productId: string) => void;
  onToggleAll: () => void;
};

export function ProductTable({
  products,
  selectedProductIds,
  onToggleProduct,
  onToggleAll,
}: ProductTableProps) {
  const allSelected = products.length > 0 && selectedProductIds.length === products.length;

  return (
    <div className="table-shell">
      <table>
        <thead>
          <tr>
            <th className="select-column">
              <input
                aria-label="Select all products"
                type="checkbox"
                checked={allSelected}
                onChange={onToggleAll}
              />
            </th>
            <th>Title</th>
            <th>Type</th>
            <th>Category</th>
            <th>Price</th>
            <th>Stock</th>
            <th>Status</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {products.map((product) => (
            <tr key={product.product_id}>
              <td className="select-column">
                <input
                  aria-label={`Select ${product.title}`}
                  type="checkbox"
                  checked={selectedProductIds.includes(product.product_id)}
                  onChange={() => onToggleProduct(product.product_id)}
                />
              </td>
              <td>
                <strong>{product.title}</strong>
                <span className="table-subtext">{product.barcode}</span>
              </td>
              <td>{product.product_type}</td>
              <td>{product.category}</td>
              <td>{formatVND(product.current_price)}</td>
              <td>{product.stock_quantity}</td>
              <td>
                {product.status === "ACTIVE" && product.stock_quantity === 0 ? (
                  <span className="status-pill status-out-of-stock">OUT OF STOCK</span>
                ) : (
                  <span className={`status-pill status-${product.status.toLowerCase()}`}>{product.status}</span>
                )}
              </td>
              <td>
                <div className="table-actions">
                  <Link className="table-action" href={`/manager/products/${product.product_id}/edit`}>
                    Edit
                  </Link>
                  <Link
                    className="table-action"
                    href={`/manager/products/history?product_id=${product.product_id}`}
                  >
                    History
                  </Link>
                </div>
              </td>
            </tr>
          ))}
          {products.length === 0 ? (
            <tr>
              <td colSpan={8} className="empty-cell">
                No products found.
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}
