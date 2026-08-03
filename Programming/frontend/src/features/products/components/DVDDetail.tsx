import type { DVDDetails } from "../types";

type DVDDetailProps = {
  details: DVDDetails;
};

/**
 * Component: DVDDetail
 *
 * Coupling/Cohesion level:
 * - Data Coupling with CustomerProduct.type_details because it receives only DVD-specific fields.
 * - Functional Cohesion because this component only renders DVD media details.
 *
 * Reason why:
 * DVD rendering stays isolated from product fetching and other media type presentation.
 */
export function DVDDetail({ details }: DVDDetailProps) {
  return (
    <dl className="detail-grid">
      <div>
        <dt>Director</dt>
        <dd>{details.director || "Not specified"}</dd>
      </div>
      <div>
        <dt>Runtime</dt>
        <dd>{details.runtime_minutes ? `${details.runtime_minutes} minutes` : "Not specified"}</dd>
      </div>
      <div>
        <dt>Disc type</dt>
        <dd>{details.disc_type || "Not specified"}</dd>
      </div>
      <div>
        <dt>Studio</dt>
        <dd>{details.studio || "Not specified"}</dd>
      </div>
      <div>
        <dt>Language</dt>
        <dd>{details.language || "Not specified"}</dd>
      </div>
      <div>
        <dt>Subtitles</dt>
        <dd>{details.subtitles || "Not specified"}</dd>
      </div>
      <div>
        <dt>Release date</dt>
        <dd>{details.release_date || "Not specified"}</dd>
      </div>
      <div>
        <dt>Genre</dt>
        <dd>{details.genre || "Not specified"}</dd>
      </div>
    </dl>
  );
}
