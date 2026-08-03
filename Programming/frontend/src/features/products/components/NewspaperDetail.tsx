import type { NewspaperDetails } from "../types";

type NewspaperDetailProps = {
  details: NewspaperDetails;
};

/**
 * Component: NewspaperDetail
 *
 * Coupling/Cohesion level:
 * - Data Coupling with CustomerProduct.type_details because it receives only newspaper-specific fields.
 * - Functional Cohesion because this component only renders newspaper media details.
 *
 * Reason why:
 * Newspaper-specific presentation remains separate from the popup coordinator and other product media views.
 */
export function NewspaperDetail({ details }: NewspaperDetailProps) {
  return (
    <dl className="detail-grid">
      <div>
        <dt>Editor-in-chief</dt>
        <dd>{details.editor_in_chief || "Not specified"}</dd>
      </div>
      <div>
        <dt>Publisher</dt>
        <dd>{details.publisher || "Not specified"}</dd>
      </div>
      <div>
        <dt>Publication date</dt>
        <dd>{details.publication_date || "Not specified"}</dd>
      </div>
      <div>
        <dt>Issue number</dt>
        <dd>{details.issue_number || "Not specified"}</dd>
      </div>
      <div>
        <dt>Publication frequency</dt>
        <dd>{details.publication_frequency || "Not specified"}</dd>
      </div>
      <div>
        <dt>ISSN</dt>
        <dd>{details.issn || "Not specified"}</dd>
      </div>
      <div>
        <dt>Language</dt>
        <dd>{details.language || "Not specified"}</dd>
      </div>
      <div className="detail-wide">
        <dt>Sections</dt>
        <dd>{details.sections || "Not specified"}</dd>
      </div>
    </dl>
  );
}
