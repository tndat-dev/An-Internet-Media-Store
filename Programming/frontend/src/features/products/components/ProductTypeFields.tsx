"use client";

import { useState } from "react";

import type { ProductType, ProductTypeDetails } from "@/features/products/types";

type ProductTypeFieldsProps = {
  productType: ProductType;
  values: ProductTypeDetails;
  onChange: (values: ProductTypeDetails) => void;
  error?: string;
};

type FieldKind = "text" | "number" | "date" | "select" | "textarea" | "tracklist";

type FieldConfig = {
  name: string;
  label: string;
  kind?: FieldKind;
  options?: string[];
  required?: boolean;
};

// `required` mirrors the backend's Problem-Statement enforcement
// (ProductService._validate_required_type_details) so the form blocks submission
// of incomplete type details before hitting the API. `options` mirrors the closed
// enumerations enforced by ProductService._validate_and_normalize_enums.
/*
 * SOLID Review
 * Principle: OCP
 * Reason: FIELD_CONFIG hard-codes every product type and subtype field inside the component module.
 * Impact: Adding a new product type or changing subtype rules requires modifying this file and can affect the shared product form.
 * Improvement: Move subtype field definitions to a registry shared with product DTO metadata or load them from backend configuration.
 */
const FIELD_CONFIG: Record<ProductType, FieldConfig[]> = {
  BOOK: [
    { name: "authors", label: "Authors", required: true },
    { name: "cover_type", label: "Cover type", kind: "select", options: ["Paperback", "Hardcover"], required: true },
    { name: "publisher", label: "Publisher", required: true },
    { name: "publication_date", label: "Publication date", kind: "date", required: true },
    { name: "pages", label: "Pages", kind: "number" },
    { name: "language", label: "Language" },
    { name: "genre", label: "Genre" },
  ],
  CD: [
    { name: "artists", label: "Artists", required: true },
    { name: "record_label", label: "Record label", required: true },
    { name: "genre", label: "Genre", required: true },
    { name: "release_date", label: "Release date", kind: "date" },
    { name: "tracklist", label: "Tracklist", kind: "tracklist", required: true },
  ],
  DVD: [
    { name: "disc_type", label: "Disc type", kind: "select", options: ["Blu-ray", "HD-DVD"], required: true },
    { name: "director", label: "Director", required: true },
    { name: "runtime_minutes", label: "Runtime minutes", kind: "number", required: true },
    { name: "studio", label: "Studio", required: true },
    { name: "language", label: "Language", required: true },
    { name: "subtitles", label: "Subtitles", required: true },
    { name: "release_date", label: "Release date", kind: "date" },
    { name: "genre", label: "Genre" },
  ],
  NEWSPAPER: [
    { name: "editor_in_chief", label: "Editor-in-chief", required: true },
    { name: "publisher", label: "Publisher", required: true },
    { name: "publication_date", label: "Publication date", kind: "date", required: true },
    { name: "issue_number", label: "Issue number" },
    { name: "publication_frequency", label: "Publication frequency" },
    { name: "issn", label: "ISSN" },
    { name: "language", label: "Language" },
    { name: "sections", label: "Sections", kind: "textarea" },
  ],
};

const WIDE_KINDS: ReadonlySet<FieldKind> = new Set(["textarea", "tracklist"]);

export function ProductTypeFields({ productType, values, onChange, error }: ProductTypeFieldsProps) {
  return (
    <fieldset className="form-section">
      <legend>Type details</legend>
      {error ? <div className="alert alert-error">{error}</div> : null}
      <div className="form-grid">
        {FIELD_CONFIG[productType].map((field) => {
          const kind = field.kind ?? "text";
          const isWide = WIDE_KINDS.has(kind);
          return (
            <label key={field.name} className={isWide ? "field field-wide" : "field"}>
              <span>
                {field.label}
                {field.required ? <span className="field-required" aria-hidden="true"> *</span> : null}
              </span>
              {renderField(field, kind, values, onChange)}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

function renderField(
  field: FieldConfig,
  kind: FieldKind,
  values: ProductTypeDetails,
  onChange: (values: ProductTypeDetails) => void,
) {
  const current = String(values[field.name] ?? "");

  function setValue(rawValue: string) {
    onChange({
      ...values,
      [field.name]: kind === "number" && rawValue ? Number(rawValue) : rawValue,
    });
  }

  if (kind === "tracklist") {
    return <TracklistField value={current} onChange={(next) => onChange({ ...values, [field.name]: next })} />;
  }

  if (kind === "textarea") {
    return <textarea required={field.required} value={current} onChange={(event) => setValue(event.target.value)} />;
  }

  if (kind === "select") {
    return (
      <select required={field.required} value={current} onChange={(event) => setValue(event.target.value)}>
        <option value="">Select…</option>
        {(field.options ?? []).map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    );
  }

  return <input type={kind} required={field.required} value={current} onChange={(event) => setValue(event.target.value)} />;
}

type Track = { title: string; length: string };

// Canonical serialised form: one track per line as "<title> — <length>" (length
// optional). Matches the backend CD.tracklist TextField; the customer detail view
// re-splits the same way.
function parseTracklist(value: string): Track[] {
  const lines = value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length === 0) {
    return [{ title: "", length: "" }];
  }
  return lines.map((line) => {
    const [title, ...rest] = line.split(/\s[—–-]\s/);
    return { title: (title ?? "").trim(), length: rest.join(" - ").trim() };
  });
}

function serializeTracklist(tracks: Track[]): string {
  return tracks
    .map((track) => ({ title: track.title.trim(), length: track.length.trim() }))
    .filter((track) => track.title || track.length)
    .map((track) => (track.length ? `${track.title} — ${track.length}` : track.title))
    .join("\n");
}

function TracklistField({ value, onChange }: { value: string; onChange: (next: string) => void }) {
  const [tracks, setTracks] = useState<Track[]>(() => parseTracklist(value));

  function commit(next: Track[]) {
    setTracks(next);
    onChange(serializeTracklist(next));
  }

  return (
    <div className="tracklist-editor">
      {tracks.map((track, index) => (
        <div className="tracklist-row" key={index}>
          <input
            className="tracklist-title"
            placeholder={`Track ${index + 1} title`}
            value={track.title}
            onChange={(event) =>
              commit(tracks.map((item, i) => (i === index ? { ...item, title: event.target.value } : item)))
            }
          />
          <input
            className="tracklist-length"
            placeholder="mm:ss"
            value={track.length}
            onChange={(event) =>
              commit(tracks.map((item, i) => (i === index ? { ...item, length: event.target.value } : item)))
            }
          />
          <button
            type="button"
            className="button button-secondary tracklist-remove"
            onClick={() => {
              const next = tracks.filter((_, i) => i !== index);
              commit(next.length ? next : [{ title: "", length: "" }]);
            }}
            aria-label={`Remove track ${index + 1}`}
          >
            Remove
          </button>
        </div>
      ))}
      <button type="button" className="button button-secondary" onClick={() => commit([...tracks, { title: "", length: "" }])}>
        Add track
      </button>
    </div>
  );
}
