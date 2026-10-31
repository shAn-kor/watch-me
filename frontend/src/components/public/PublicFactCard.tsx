import type {
  ClipLength,
  FactNotice,
  FactSource,
  PublicEvidence,
} from "../../api/types";
import { sortEvidence } from "../../lib/evidence";
import { RangePlayer } from "../RangePlayer";
import { formatDay } from "./format";
import { usePublicPlayer } from "./PublicPlayerContext";

export interface PublicFactView {
  id: string;
  behavior: string;
  source: FactSource;
  source_label: string;
  observed_on: string;
  confirmed_by_label: string;
  clip_length: ClipLength;
  notice: FactNotice | null;
  evidence: PublicEvidence[];
}

/**
 * One public fact (PUB-2, PUB-3). All model and shelter text is a React text
 * node. The player is the page-wide shared one: opening a card closes the other.
 */
export function PublicFactCard({
  fact,
  scope,
  situationLabel,
}: {
  fact: PublicFactView;
  /** Keeps the same fact listed twice (facts and answer) from opening twice. */
  scope: string;
  situationLabel?: string;
}) {
  const { active, open, close } = usePublicPlayer();
  const key = `${scope}:${fact.id}`;
  const mine = active?.key === key ? active : null;
  const ranges = sortEvidence(fact.evidence);
  const range = mine ? ranges[mine.range] : undefined;
  const staffNote = fact.source === "staff_note" || ranges.length === 0;

  return (
    <li className="public-fact">
      {situationLabel && (
        <p className="public-fact__situation">{situationLabel}</p>
      )}
      <p className="public-fact__text" style={{ whiteSpace: "pre-line" }}>
        {fact.behavior}
      </p>
      <p className="public-fact__meta">
        {staffNote ? "" : `${fact.clip_length.label} - `}
        {fact.source_label}
      </p>
      <p className="public-fact__meta">Observed {formatDay(fact.observed_on)}</p>
      <p className="public-fact__meta">{fact.confirmed_by_label}</p>
      {fact.notice && <p className="wm-notice">{fact.notice.text}</p>}
      {fact.source === "narration" && (
        <p>The volunteer says this in the clip. The clip may not show it.</p>
      )}
      {staffNote ? (
        <p className="public-fact__meta">No clip.</p>
      ) : (
        <div className="wm-row">
          {ranges.map((_, i) => {
            const label =
              ranges.length === 1 ? "Play clip" : `Play range ${i + 1}`;
            return (
              <button
                key={i}
                type="button"
                className="wm-btn wm-btn--secondary"
                aria-label={`${label} for: ${fact.behavior}`}
                aria-expanded={
                  mine !== null && (ranges.length === 1 || mine.range === i)
                }
                onClick={() => open({ key, range: i })}
              >
                {label}
              </button>
            );
          })}
        </div>
      )}
      {mine && range && (
        <div>
          <RangePlayer
            src={range.media_url}
            captionsSrc={range.captions_url}
            startS={range.start_s}
            endS={range.end_s}
            autoplay
          />
          <button
            type="button"
            className="wm-btn wm-btn--secondary"
            onClick={close}
          >
            Close
          </button>
        </div>
      )}
    </li>
  );
}
