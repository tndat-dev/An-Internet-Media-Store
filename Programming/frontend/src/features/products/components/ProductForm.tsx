"use client";

import { FormEvent, useMemo, useState } from "react";
import Link from "next/link";

import type { Product, ProductPayload, ProductType, ProductTypeDetails } from "@/features/products/types";
import { ApiError, parseApiError } from "@/lib/apiClient";
import { PRICE_RATIO_MAX, PRICE_RATIO_MIN } from "@/lib/constants";

import { ProductTypeFields } from "./ProductTypeFields";

type ProductFormProps = {
  initialProduct?: Product;
  mode: "create" | "edit";
  onSubmit: (payload: ProductPayload) => Promise<void>;
};

const productTypes: Array<{ value: ProductType; label: string }> = [
  { value: "BOOK", label: "Book" },
  { value: "CD", label: "CD" },
  { value: "DVD", label: "DVD" },
  { value: "NEWSPAPER", label: "Newspaper" },
];

function initialState(product?: Product): ProductPayload {
  return {
    product_type: product?.product_type ?? "BOOK",
    title: product?.title ?? "",
    category: product?.category ?? "",
    general_description: product?.general_description ?? "",
    height: product?.height ?? "",
    width: product?.width ?? "",
    length: product?.length ?? "",
    weight: product?.weight ?? "",
    barcode: product?.barcode ?? "",
    image_url: product?.image_url ?? "",
    original_value: product?.original_value ?? "",
    current_price: product?.current_price ?? "",
    stock_quantity: product?.stock_quantity ?? 0,
    status: product?.status ?? "ACTIVE",
    type_details: product?.type_details ?? {},
    stock_adjustment_reason: "",
  };
}

// Turn an unknown thrown error into a clean banner message (never the raw
// "API request failed: {json}" string the legacy ApiError.message carries).
function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (typeof error.body === "string" && error.body) {
      return error.body;
    }
    if (Array.isArray(error.body) && error.body.length > 0) {
      return error.body.map(String).join(" ");
    }
  }
  return "Could not save product. Please check the highlighted fields.";
}

export function ProductForm({ initialProduct, mode, onSubmit }: ProductFormProps) {
  const [form, setForm] = useState<ProductPayload>(() => initialState(initialProduct));
  const [typeDetails, setTypeDetails] = useState<ProductTypeDetails>(initialProduct?.type_details ?? {});
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  const priceHint = useMemo(() => {
    const originalValue = Number(form.original_value);
    if (!originalValue) {
      return `Allowed price: ${PRICE_RATIO_MIN * 100}% to ${PRICE_RATIO_MAX * 100}% of original value`;
    }
    const min = (originalValue * PRICE_RATIO_MIN).toLocaleString();
    const max = (originalValue * PRICE_RATIO_MAX).toLocaleString();
    return `Allowed price: ${min} - ${max} VND`;
  }, [form.original_value]);

  function updateField(field: keyof ProductPayload, value: string | number) {
    setForm((current) => ({
      ...current,
      [field]: value,
    }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setFieldErrors({});
    setIsSubmitting(true);

    try {
      await onSubmit({
        ...form,
        stock_quantity: Number(form.stock_quantity),
        type_details: typeDetails,
      });
    } catch (submitError) {
      const fields = parseApiError(submitError);
      setFieldErrors(fields);
      const general = fields.detail ?? fields.non_field_errors;
      if (general) {
        setError(general);
      } else if (Object.keys(fields).length > 0) {
        setError("Please fix the highlighted fields below.");
      } else {
        setError(describeError(submitError));
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  const errorClass = (name: string) => (fieldErrors[name] ? "input-error" : undefined);
  const renderFieldError = (name: string) =>
    fieldErrors[name] ? <span className="field-error">{fieldErrors[name]}</span> : null;

  return (
    <form className="workspace-card product-form" onSubmit={handleSubmit}>
      {/*
        SOLID Review
        Principle: SRP/OCP
        Reason: ProductForm owns form state, price hint calculation, product-type switching, payload shaping, and create/edit UI in one component.
        Impact: Product validation, subtype-field changes, and form layout changes can all require edits here, reducing maintainability.
        Improvement: Extract product form state/validation into a hook and delegate subtype behavior to a field registry.
      */}
      <div className="form-header">
        <div>
          <p className="eyebrow">Product Manager</p>
          <h1>{mode === "create" ? "Create product" : "Update product"}</h1>
        </div>
        <Link href="/manager/products" className="button button-secondary">
          Back
        </Link>
      </div>

      {error ? <div className="alert alert-error">{error}</div> : null}

      <fieldset className="form-section">
        <legend>Product information</legend>
        <div className="form-grid">
          <label className="field">
            <span>Product type</span>
            <select
              value={form.product_type}
              onChange={(event) => {
                updateField("product_type", event.target.value as ProductType);
                setTypeDetails({});
              }}
            >
              {productTypes.map((type) => (
                <option key={type.value} value={type.value}>
                  {type.label}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Title</span>
            <input
              className={errorClass("title")}
              value={form.title}
              onChange={(event) => updateField("title", event.target.value)}
              required
            />
            {renderFieldError("title")}
          </label>
          <label className="field">
            <span>Category</span>
            <input
              className={errorClass("category")}
              value={form.category}
              onChange={(event) => updateField("category", event.target.value)}
              required
            />
            {renderFieldError("category")}
          </label>
          <label className="field">
            <span>Barcode</span>
            <input
              className={errorClass("barcode")}
              value={form.barcode}
              onChange={(event) => updateField("barcode", event.target.value)}
              required
            />
            {renderFieldError("barcode")}
          </label>
          <label className="field field-wide">
            <span>Description</span>
            <textarea
              value={form.general_description}
              onChange={(event) => updateField("general_description", event.target.value)}
            />
          </label>
          <label className="field field-wide">
            <span>Image URL</span>
            <input
              className={errorClass("image_url")}
              value={form.image_url}
              onChange={(event) => updateField("image_url", event.target.value)}
            />
            {renderFieldError("image_url")}
          </label>
        </div>
      </fieldset>

      <fieldset className="form-section">
        <legend>Pricing, stock, and dimensions</legend>
        <div className="form-grid">
          <label className="field">
            <span>Original value</span>
            <input
              type="number"
              min="0"
              className={errorClass("original_value")}
              value={form.original_value}
              onChange={(event) => updateField("original_value", event.target.value)}
              required
            />
            {renderFieldError("original_value")}
          </label>
          <label className="field">
            <span>Current price</span>
            <input
              type="number"
              min="0"
              className={errorClass("current_price")}
              value={form.current_price}
              onChange={(event) => updateField("current_price", event.target.value)}
              required
            />
            {renderFieldError("current_price") ?? <small>{priceHint}</small>}
          </label>
          <label className="field">
            <span>Stock quantity</span>
            <input
              type="number"
              min="0"
              className={errorClass("stock_quantity")}
              value={form.stock_quantity}
              onChange={(event) => updateField("stock_quantity", Number(event.target.value))}
              required
            />
            {renderFieldError("stock_quantity")}
          </label>
          <label className="field">
            <span>Status</span>
            <select value={form.status} onChange={(event) => updateField("status", event.target.value)}>
              <option value="ACTIVE">Active</option>
              <option value="DEACTIVATED">Deactivated</option>
            </select>
          </label>
          <label className="field">
            <span>Height (cm)</span>
            <input
              className={errorClass("height")}
              value={form.height}
              onChange={(event) => updateField("height", event.target.value)}
              required
            />
            {renderFieldError("height")}
          </label>
          <label className="field">
            <span>Width (cm)</span>
            <input
              className={errorClass("width")}
              value={form.width}
              onChange={(event) => updateField("width", event.target.value)}
              required
            />
            {renderFieldError("width")}
          </label>
          <label className="field">
            <span>Length (cm)</span>
            <input
              className={errorClass("length")}
              value={form.length}
              onChange={(event) => updateField("length", event.target.value)}
              required
            />
            {renderFieldError("length")}
          </label>
          <label className="field">
            <span>Weight (kg)</span>
            <input
              className={errorClass("weight")}
              value={form.weight}
              onChange={(event) => updateField("weight", event.target.value)}
              required
            />
            {renderFieldError("weight")}
          </label>
          {mode === "edit" ? (
            <label className="field field-wide">
              <span>Stock adjustment reason</span>
              <input
                className={errorClass("stock_adjustment_reason")}
                value={form.stock_adjustment_reason}
                onChange={(event) => updateField("stock_adjustment_reason", event.target.value)}
                placeholder="Required when stock quantity changes"
              />
              {renderFieldError("stock_adjustment_reason")}
            </label>
          ) : null}
        </div>
      </fieldset>

      <ProductTypeFields
        productType={form.product_type}
        values={typeDetails}
        onChange={setTypeDetails}
        error={fieldErrors.type_details}
      />

      <div className="form-actions">
        <button type="submit" className="button button-primary" disabled={isSubmitting}>
          {isSubmitting ? "Saving..." : mode === "create" ? "Create product" : "Save changes"}
        </button>
      </div>
    </form>
  );
}
