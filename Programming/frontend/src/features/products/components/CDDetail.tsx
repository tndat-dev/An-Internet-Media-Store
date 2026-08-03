import type { CDDetails } from "../types";

type CDDetailProps = {
  details: CDDetails;
};

/**
 * Component: CDDetail
 *
 * Coupling/Cohesion level:
 * - Data Coupling with CustomerProduct.type_details because it receives only CD-specific fields.
 * - Functional Cohesion because this component only renders CD media details.
 *
 * Reason why:
 * Keeping CD fields here prevents ProductDetailPopup from becoming a logical-cohesion component with many unrelated media branches.
 */
export function CDDetail({ details }: CDDetailProps) {
  const tracks = (details.tracklist ?? "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  return (
    <dl className="detail-grid">
      <div>
        <dt>Artists</dt>
        <dd>{details.artists || "Not specified"}</dd>
      </div>
      <div>
        <dt>Record label</dt>
        <dd>{details.record_label || "Not specified"}</dd>
      </div>
      <div>
        <dt>Genre</dt>
        <dd>{details.genre || "Not specified"}</dd>
      </div>
      <div>
        <dt>Release date</dt>
        <dd>{details.release_date || "Not specified"}</dd>
      </div>
      <div className="detail-wide">
        <dt>Tracklist</dt>
        <dd>
          {tracks.length > 0 ? (
            <ol className="tracklist-display">
              {tracks.map((track, index) => (
                <li key={index}>{track}</li>
              ))}
            </ol>
          ) : (
            "Not specified"
          )}
        </dd>
      </div>
    </dl>
  );
}
