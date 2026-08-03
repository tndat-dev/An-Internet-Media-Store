/**
 * Money formatting utility
 *
 * Vietnamese currency formatting using VND locale and currency format
 */

/**
 * Format amount as Vietnamese Dong (VND)
 *
 * @param amount - Numeric amount or string representation
 * @returns Formatted string with VND locale
 */
export function formatVND(amount: string | number): string {
  const numAmount = typeof amount === "string" ? parseFloat(amount) : amount;

  if (isNaN(numAmount)) {
    return "0 VND";
  }

  return numAmount.toLocaleString("vi-VN", {
    style: "currency",
    currency: "VND",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  });
}

/**
 * Format amount without currency symbol (just thousand separators)
 *
 * @param amount - Numeric amount or string representation
 * @returns Formatted string
 */
export function formatNumber(amount: string | number): string {
  const numAmount = typeof amount === "string" ? parseFloat(amount) : amount;

  if (isNaN(numAmount)) {
    return "0";
  }

  return numAmount.toLocaleString("vi-VN", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  });
}

/**
 * Parse amount string to number, handling Vietnamese locale
 *
 * @param amount - String representation of amount
 * @returns Parsed number
 */
export function parseAmount(amount: string): number {
  // Replace Vietnamese thousand separator with nothing, then decimal
  const normalized = amount.replace(/\./g, "").replace(",", ".");
  return parseFloat(normalized) || 0;
}
