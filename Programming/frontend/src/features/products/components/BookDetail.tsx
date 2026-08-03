import type { BookDetails } from "../types";

type BookDetailProps = {
  details: BookDetails;
};

/**
 * Component: BookDetail
 *
 * Coupling/Cohesion level:
 * - Data Coupling with CustomerProduct.type_details because it receives only book-specific fields.
 * - Functional Cohesion because this component only renders book media details.
 *
 * Reason why:
 * ProductDetailPopup coordinates the modal while this component keeps book rendering separate from CD/DVD/Newspaper rendering.
 */
export function BookDetail({ details }: BookDetailProps) {
  return (
    <dl className="detail-grid">
      <div>
        <dt>Author</dt>
        <dd>{details.authors || "Not specified"}</dd>
      </div>
      <div>
        <dt>Cover</dt>
        <dd>{details.cover_type || "Not specified"}</dd>
      </div>
      <div>
        <dt>Publisher</dt>
        <dd>{details.publisher || "Not specified"}</dd>
      </div>
      <div>
        <dt>Date</dt>
        <dd>{details.publication_date || "Not specified"}</dd>
      </div>
      <div>
        <dt>Pages</dt>
        <dd>{details.pages ? `${details.pages} pages` : "Not specified"}</dd>
      </div>
      <div>
        <dt>Language</dt>
        <dd>{details.language || "Not specified"}</dd>
      </div>
      <div>
        <dt>Genre</dt>
        <dd>{details.genre || "Not specified"}</dd>
      </div>
    </dl>
  );
}
