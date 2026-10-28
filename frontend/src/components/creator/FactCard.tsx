import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { isApiError } from "../../api/errors";
import { useApi } from "../../api/provider";
import type { Evidence, Fact, FactFlag, WordingCheck } from "../../api/types";
import { SITUATION_LABELS } from "../../lib/constants";
import { formatClock } from "../../lib/time";
import { RangePlayer } from "../RangePlayer";
import type { RangeReport } from "../RangeTracker";
import { FactStatusChip, OriginChip } from "./Chips";
import { describeError } from "./errors";
import { formatDay, round01 } from "./format";
import { useToast } from "./Toast";

type Local =
  | { kind: "saved" }
  | { kind: "none" }
  | { kind: "unsaved"; report: RangeReport };

type RangeState = "watched" | "unsaved" | "none";

const RANGE_TEXT: Record<RangeState, string> = {
  watched: "Watched",
  unsaved: "Watched, not saved",
  none: "Not watched",
};

export const SOURCE_TEXT = {
  clip: "Seen in clip",
  narration: "Said by volunteer, not in clip",
  staff_note: "Shelter staff note",
} as const;

/** A warn flag needs the wording box. Unknown severities count as warn. */
export function isWarnFlag(f: FactFlag, mode: WordingCheck): boolean {
  if (f.severity === "info") return false;
  if (mode === "rules_only" && f.code === "trait_claim") return false;
  return true;
}

function FlagNotice({ fact, mode }: { fact: Fact; mode: WordingCheck }) {
  const unavailable = fact.flags.some((f) => f.code === "check_unavailable");
  const real = fact.flags.filter(
    (f) => f.code !== "check_unavailable" && isWarnFlag(f, mode),
  );
  if (real.length === 0 && !unavailable) return null;
  return (
    <>
      {real.length > 0 ? (
        <div className="wm-notice wm-notice--warn">
          {mode === "model" ? (
            <p className="wm-strong">
              Wording check: this text may state a trait, not something you can
              see in the clip.
            </p>
          ) : null}
          {real.map((f, i) => (
            <p key={`${f.code}-${i}`}>
              {mode === "model" ? f.detail : `Wording check: ${f.detail}`}
            </p>
          ))}
        </div>
      ) : null}
      {unavailable ? (
        <div className="wm-notice wm-notice--info">
          <p>
            The wording check could not run for this fact. Read the text
            yourself.
          </p>
        </div>
      ) : null}
    </>
  );
}

const SERVER_TEXT: Record<string, string> = {
  staff_only_situation: "Only staff can confirm facts about children or cats.",
  not_own_session: "You can confirm only facts from your own sessions.",
  forbidden_role: "Only staff can confirm a staff note.",
  publish_checklist_incomplete:
    "This dog is published but its people check is missing. Ask staff to unpublish the dog and finish the checklist.",
  invalid_state: "This fact is not a draft. Reload the page.",
};

export interface FactCardProps {
  fact: Fact;
  wordingMode: WordingCheck;
  canEdit: boolean;
  dogPublished: boolean;
  /** Reload the list from the server. */
  onReload: () => void;
  onEdit: (fact: Fact) => void;
  onDelete: (fact: Fact) => void;
  /** After a confirm; the page says so in its live region. */
  onConfirmed: (fact: Fact) => void;
}

export function FactCard({
  fact,
  wordingMode,
  canEdit,
  dogPublished,
  onReload,
  onEdit,
  onDelete,
  onConfirmed,
}: FactCardProps) {
  const api = useApi();
  const toast = useToast();
  const uid = useId();
  const headId = `fact-h-${fact.id}`;
  const reasonId = `${uid}-reason`;

  const [local, setLocal] = useState<Record<string, Local>>({});
  const [idx, setIdx] = useState(0);
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const [opened, setOpened] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [consentLink, setConsentLink] = useState(false);

  const draft = fact.status === "draft";
  const ranges = fact.evidence;
  const multi = ranges.length > 1;
  const current: Evidence | undefined =
    ranges[Math.min(idx, ranges.length - 1)];

  const stateOf = (ev: Evidence): RangeState => {
    const l = local[ev.id];
    if (l) return l.kind === "saved" ? "watched" : l.kind;
    return ev.played_by_me ? "watched" : "none";
  };

  const report = async (ev: Evidence, r: RangeReport) => {
    const body = {
      evidence_id: ev.id,
      position_s: round01(r.positionS),
      watched_s: round01(r.watchedS),
    };
    setProblem(null);
    try {
      await api.playbackComplete(fact.id, body);
      setLocal((s) => ({ ...s, [ev.id]: { kind: "saved" } }));
    } catch (e) {
      if (!isApiError(e)) {
        setLocal((s) => ({ ...s, [ev.id]: { kind: "unsaved", report: r } }));
        return;
      }
      if (e.code === "not_found") {
        setProblem("This fact no longer exists. The list will reload.");
        onReload();
      } else if (e.code === "invalid_state") {
        setProblem("This fact is not a draft anymore. The list will reload.");
        onReload();
      } else if (e.code === "not_own_session") {
        setProblem(
          "You can record watching only for facts from your own sessions, or as staff.",
        );
      } else if (e.code === "validation_error") {
        setProblem(
          "That play did not count. Watch the whole range without skipping.",
        );
        setLocal((s) => ({ ...s, [ev.id]: { kind: "none" } }));
      } else {
        setProblem(describeError(e).text);
        setLocal((s) => ({ ...s, [ev.id]: { kind: "unsaved", report: r } }));
      }
    }
  };

  const save = (ev: Evidence) => {
    const l = local[ev.id];
    if (l?.kind === "unsaved") void report(ev, l.report);
  };

  const states = ranges.map(stateOf);
  const hasWarn = fact.flags.some((f) => isWarnFlag(f, wordingMode));
  const allWatched = states.every((s) => s === "watched");
  const anyUnsaved = states.includes("unsaved");

  let reason: string | null = null;
  let consentReason = false;
  if (draft) {
    const hard = fact.blocked_reason;
    if (
      !fact.can_confirm &&
      hard &&
      hard !== "playback_required" &&
      hard !== "flags_unacknowledged"
    ) {
      if (hard === "consent_required") {
        reason = "Accept the consent notice to confirm facts.";
        consentReason = true;
      } else {
        reason = SERVER_TEXT[hard] ?? "You cannot confirm this fact now.";
      }
    } else if (anyUnsaved) {
      reason = "Save your watch progress to confirm.";
    } else if (!allWatched) {
      reason =
        ranges.length >= 3
          ? "Watch all ranges to confirm."
          : multi
            ? "Watch both ranges to confirm."
            : "Watch the whole range to confirm.";
    } else if (hasWarn && !ack) {
      reason = "Tick the wording box to confirm.";
    }
  }
  const blocked = reason !== null || busy;

  const confirm = async () => {
    if (blocked) return;
    setBusy(true);
    setProblem(null);
    setConsentLink(false);
    try {
      await api.confirmFact(fact.id, hasWarn);
      toast.success(
        dogPublished
          ? "Fact confirmed. It is on the public profile now."
          : "Fact confirmed.",
      );
      onConfirmed(fact);
    } catch (e) {
      if (isApiError(e) && e.code === "playback_required") {
        const missing = e.details.missing_evidence_ids;
        setLocal((s) => {
          const next = { ...s };
          for (const ev of ranges) {
            if (!missing || missing.includes(ev.id))
              next[ev.id] = { kind: "none" };
          }
          return next;
        });
        setProblem("Watch the whole range before you confirm.");
        onReload();
      } else if (isApiError(e) && e.code === "invalid_state") {
        setProblem(
          "This fact changed since you opened it. The list will reload.",
        );
        onReload();
      } else if (isApiError(e) && e.code === "not_found") {
        setProblem("This fact no longer exists. The list will reload.");
        onReload();
      } else if (isApiError(e) && e.code === "flags_unacknowledged") {
        setProblem("Tick the wording box before you confirm.");
      } else {
        const info = describeError(e, {
          consent_required: "Accept the consent notice to confirm facts.",
          ...Object.fromEntries(
            Object.entries(SERVER_TEXT).filter(([k]) => k !== "invalid_state"),
          ),
        });
        setProblem(info.text);
        setConsentLink(info.consentLink);
      }
    } finally {
      setBusy(false);
    }
  };

  const confirmedLine =
    fact.confirmed !== null
      ? `Confirmed by ${fact.confirmed.by_name}, ${fact.confirmed.role}, ${formatDay(fact.confirmed.at.slice(0, 10))}`
      : "Confirmed";

  const player = (ev: Evidence, withReport: boolean) =>
    ev.media_url ? (
      <RangePlayer
        src={ev.media_url}
        captionsSrc={ev.captions_url}
        startS={ev.start_s}
        endS={ev.end_s}
        onRangeComplete={withReport ? (r) => void report(ev, r) : undefined}
      />
    ) : (
      <p className="wm-muted">This clip is not available.</p>
    );

  return (
    <article aria-labelledby={headId} className="wm-card wm-fact">
      <div className="wm-row wm-row--between">
        <h2 id={headId} tabIndex={-1}>
          {SITUATION_LABELS[fact.situation]}
        </h2>
        <FactStatusChip status={fact.status} />
      </div>
      <div className="wm-row">
        <OriginChip origin={fact.origin} />
        {fact.situation === "children_cats" ? (
          <span className="wm-chip wm-chip--plain">Staff confirm only</span>
        ) : null}
      </div>

      <p className="wm-fact__text">{fact.behavior}</p>

      <FlagNotice fact={fact} mode={wordingMode} />

      <p className="wm-muted">
        <span>{SOURCE_TEXT[fact.source]}</span>
        {fact.clip_length.label ? (
          <span>{` - ${fact.clip_length.label}`}</span>
        ) : null}
        <span>{` - Observed ${formatDay(fact.observed_on)}`}</span>
      </p>

      {fact.source === "staff_note" || ranges.length === 0 ? (
        <p>No clip. This is a staff note.</p>
      ) : (
        <>
          {fact.source === "narration" ? (
            <p>This fact comes from narration. Turn sound on.</p>
          ) : null}
          {multi ? (
            <div className="wm-row" role="group" aria-label="Clip ranges">
              {ranges.map((ev, i) => (
                <button
                  key={ev.id}
                  type="button"
                  className="wm-btn wm-btn--secondary"
                  aria-pressed={i === idx}
                  onClick={() => setIdx(i)}
                >
                  {`Range ${i + 1} of ${ranges.length} ${formatClock(ev.start_s)}-${formatClock(ev.end_s)} `}
                  {draft ? (
                    <span data-range-state className="wm-range-state">
                      {RANGE_TEXT[states[i] ?? "none"]}
                    </span>
                  ) : null}
                </button>
              ))}
            </div>
          ) : null}
          {draft ? (
            <>
              {current ? player(current, true) : null}
              {!multi && current ? (
                <div className="wm-row wm-row--between">
                  <span data-range-state className="wm-range-state">
                    {RANGE_TEXT[states[0] ?? "none"]}
                  </span>
                  {states[0] === "unsaved" ? (
                    <button
                      type="button"
                      className="wm-btn wm-btn--secondary"
                      onClick={() => save(current)}
                    >
                      Save
                    </button>
                  ) : null}
                </div>
              ) : null}
              {multi &&
              current &&
              states[Math.min(idx, ranges.length - 1)] === "unsaved" ? (
                <button
                  type="button"
                  className="wm-btn wm-btn--secondary"
                  onClick={() => save(current)}
                >
                  Save
                </button>
              ) : null}
            </>
          ) : (
            <>
              <button
                type="button"
                className="wm-btn wm-btn--secondary"
                aria-expanded={opened}
                onClick={() => setOpened((o) => !o)}
              >
                {opened ? "Hide range" : "Watch range"}
              </button>
              {opened && current ? player(current, false) : null}
            </>
          )}
        </>
      )}

      {draft && hasWarn ? (
        <div className="wm-check">
          <input
            id={`${uid}-ack`}
            type="checkbox"
            checked={ack}
            onChange={(e) => setAck(e.target.checked)}
          />
          <label htmlFor={`${uid}-ack`}>I checked the wording.</label>
        </div>
      ) : null}

      {draft ? (
        <div className="wm-stack">
          <button
            type="button"
            className="wm-btn"
            aria-disabled={blocked ? "true" : undefined}
            aria-describedby={reason ? reasonId : undefined}
            onClick={() => void confirm()}
          >
            {busy ? "Confirming..." : "Confirm"}
          </button>
          {reason ? (
            <p id={reasonId} className="wm-muted">
              {reason}
              {consentReason ? (
                <>
                  {" "}
                  <Link to="/app/consent">Open consent notice</Link>
                </>
              ) : null}
            </p>
          ) : null}
        </div>
      ) : (
        <p className="wm-strong">{confirmedLine}</p>
      )}

      {problem ? (
        <p role="alert" className="wm-error-text">
          {problem}
          {consentLink ? (
            <>
              {" "}
              <Link to="/app/consent">Open consent notice</Link>
            </>
          ) : null}
        </p>
      ) : null}

      <div className="wm-row">
        <button
          type="button"
          className="wm-btn wm-btn--secondary"
          disabled={!canEdit}
          onClick={() => onEdit(fact)}
        >
          Edit
        </button>
        <button
          type="button"
          className="wm-btn wm-btn--danger"
          disabled={!canEdit}
          onClick={() => onDelete(fact)}
        >
          Delete
        </button>
      </div>
    </article>
  );
}
