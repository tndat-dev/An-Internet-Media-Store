"use client";

type ProductDeleteDialogProps = {
  count: number;
  isOpen: boolean;
  isDeleting: boolean;
  onCancel: () => void;
  onConfirm: () => void;
};

export function ProductDeleteDialog({
  count,
  isOpen,
  isDeleting,
  onCancel,
  onConfirm,
}: ProductDeleteDialogProps) {
  if (!isOpen) {
    return null;
  }

  return (
    <div className="modal-backdrop" role="presentation">
      {/*
        SOLID Review
        Principle: SRP
        Reason: ProductDeleteDialog currently renders confirmation UI and repeats delete/deactivate business-rule text from the backend.
        Impact: If delete policy changes, UI copy can drift from backend behavior and create misleading manager feedback.
        Improvement: Keep the dialog focused on confirmation and pass policy copy/status from a higher-level product management view or API metadata.
      */}
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="delete-products-title">
        <h2 id="delete-products-title">Delete selected products</h2>
        <p>
          The system will mark products with stock as deactivated. Products with zero stock will be marked deleted.
        </p>
        <p className="rule-note">Request limit: 10 products. Daily manager limit: 20 products.</p>
        <div className="modal-actions">
          <button type="button" className="button button-secondary" onClick={onCancel} disabled={isDeleting}>
            Cancel
          </button>
          <button type="button" className="button button-danger" onClick={onConfirm} disabled={isDeleting || count === 0}>
            {isDeleting ? "Deleting..." : `Delete ${count}`}
          </button>
        </div>
      </section>
    </div>
  );
}
