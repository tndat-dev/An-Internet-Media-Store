"use client";

import type { CartItem } from "../types";

type CartItemRowProps = {
  item: CartItem;
  isBusy: boolean;
  onQuantityChange: (cartItemId: string, quantity: number) => void;
  onRemove: (cartItemId: string) => void;
};

function formatCurrency(value: string | number) {
  return `${Number(value).toLocaleString()} VND`;
}

export function CartItemRow({ item, isBusy, onQuantityChange, onRemove }: CartItemRowProps) {
  /*
   * Coupling/Cohesion: renders a single cart line item and delegates
   * quantity/remove actions to the parent screen. It stays focused on row
   * presentation only.
   */
  return (
    <tr>
      <td>
        <strong>{item.productTitle}</strong>
        <span className="table-subtext">{item.productType}</span>
        {item.stockWarning ? (
          <span className="field-error">
            Available quantity is {item.stockWarning.availableQuantity}; you requested {item.quantity}, so {item.stockWarning.missingQuantity} item(s) must be removed before checkout.
          </span>
        ) : null}
      </td>
      <td>{formatCurrency(item.unitPrice)}</td>
      <td>
        <input
          className="quantity-input"
          aria-label={`Quantity for ${item.productTitle}`}
          min={1}
          type="number"
          value={item.quantity}
          disabled={isBusy}
          onChange={(event) => onQuantityChange(item.cartItemId, Number(event.target.value))}
        />
      </td>
      <td>{formatCurrency(item.lineSubtotal)}</td>
      <td>{item.stockQuantity}</td>
      <td>
        <button
          type="button"
          className="table-action button-link"
          disabled={isBusy}
          onClick={() => onRemove(item.cartItemId)}
        >
          Remove
        </button>
      </td>
    </tr>
  );
}
