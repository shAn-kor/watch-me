import { useRef, useState } from "react";
import { isApiError } from "../../api/errors";
import { useApi } from "../../api/provider";
import type { Clip, EvidenceInput, Fact, Situation } from "../../api/types";
import { SITUATIONS } from "../../lib/constants";
import { formatClock, roundTenth } from "../../lib/time";
import { RangePlayer } from "../RangePlayer";
import { Dialog } from "./Dialog";
import { ErrorNotice, type ErrorTable } from "./errors";
import { todayLocal } from "./format";
import { useToast } from "./Toast";
import { Field } from "./ui";

const BEHAVIOR_HELP =
  "Write what a viewer can see or hear, for example how many times, or what the dog does next.";
const BEHAVIOR_TEXT = "Write between 3 and 280 characters.";
const EVIDENCE_TEXT =
  "A range is outside its clip, shorter than 1 s, or longer than 60 s. Fix the ranges and save again.";
const CLIP_NOT_READY =
  "One of the clips is still processing. Try again when it is ready.";
const MAX_RANGES = 3;

interface RangeDraft {
  key: string;
  id?: string;
  clipId: string;
  start: string;
  end: string;
}

let keySeq = 0;
const nextKey = () => `r${++keySeq}`;

function num(s: string): number {
  return s.trim() === "" ? Number.NaN : Number(s);
}

function behaviorProblem(text: string): string | null {
  if (/[\r\n]/.test(text)) return "Use one line.";
  const n = text.trim().length;
  return n < 3 || n > 280 ? BEHAVIOR_TEXT : null;
}

function rangeProblem(r: RangeDraft, clips: Clip[]): string | null {
  if (!r.clipId) return "Choose a clip.";
  const s = num(r.start);
  const e = num(r.end);
  if (Number.isNaN(s) || Number.isNaN(e) || s < 0)
    return "Enter a start and an end time in seconds.";
  if (e <= s) return "The end must be after the start.";
  if (e - s < 1 || e - s > 60) return "A range must be 1 to 60 seconds long.";
  const clip = clips.find((c) => c.id === r.clipId);
  if (clip && clip.duration_s > 0 && e > clip.duration_s + 0.05)
    return "The end is past the end of the clip.";
  return null;
}

function SituationSelect({
  value,
  onChange,
  error,
}: {
  value: Situation | "";
  onChange: (v: Situation | "") => void;
  error?: string | null;
}) {
  return (
    <Field label="Situation" error={error}>
      {({ id, describedBy, invalid }) => (
        <select
          id={id}
          value={value}
          aria-describedby={describedBy}
          aria-invalid={invalid || undefined}
          onChange={(e) => onChange(e.target.value as Situation | "")}
        >
          <option value="">Choose a situation</option>
          {SITUATIONS.map((s) => (
            <option key={s.code} value={s.code}>
              {s.label}
            </option>
          ))}
        </select>
      )}
    </Field>
  );
}

function BehaviorField({
  value,
  onChange,
  error,
}: {
  value: string;
  onChange: (v: string) => void;
  error?: string | null;
}) {
  return (
    <Field
      label="What happens in the clip"
      help={`3 to 280 characters, one line. ${value.length} / 280. ${BEHAVIOR_HELP}`}
      error={error}
    >
      {({ id, describedBy, invalid }) => (
        <textarea
          id={id}
          rows={3}
          value={value}
          aria-describedby={describedBy}
          aria-invalid={invalid || undefined}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </Field>
  );
}

function clipLabel(c: Clip): string {
  return `Clip ${c.ordinal} - ${c.original_filename} - ${formatClock(c.duration_s)}`;
}

/** One range: clip select, preview player, start and end with "Use current time". */
function RangeRow({
  range,
  clips,
  error,
  canRemove,
  onChange,
  onRemove,
}: {
  range: RangeDraft;
  clips: Clip[];
  error: string | null;
  canRemove: boolean;
  onChange: (next: RangeDraft) => void;
  onRemove: () => void;
}) {
  const position = useRef(0);
  const clip = clips.find((c) => c.id === range.clipId);
  const len = num(range.end) - num(range.start);
  return (
    <div className="wm-stack wm-range-row">
      <Field label="Clip" error={error}>
        {({ id, describedBy, invalid }) => (
          <select
            id={id}
            value={range.clipId}
            aria-describedby={describedBy}
            aria-invalid={invalid || undefined}
            onChange={(e) => onChange({ ...range, clipId: e.target.value })}
          >
            <option value="">Choose a clip</option>
            {clips.map((c) => (
              <option key={c.id} value={c.id}>
                {clipLabel(c)}
              </option>
            ))}
          </select>
        )}
      </Field>
      {clip?.media_url ? (
        <RangePlayer
          src={clip.media_url}
          captionsSrc={clip.captions_url}
          startS={0}
          endS={clip.duration_s}
          onProgress={(p) => {
            position.current = p;
          }}
        />
      ) : null}
      <Field label="Start (s)">
        {({ id }) => (
          <div className="wm-row">
            <input
              id={id}
              type="number"
              inputMode="decimal"
              min={0}
              step={0.1}
              value={range.start}
              onChange={(e) => onChange({ ...range, start: e.target.value })}
            />
            <button
              type="button"
              className="wm-btn wm-btn--secondary"
              onClick={() =>
                onChange({
                  ...range,
                  start: String(roundTenth(position.current)),
                })
              }
            >
              Use current time
            </button>
          </div>
        )}
      </Field>
      <Field label="End (s)">
        {({ id }) => (
          <div className="wm-row">
            <input
              id={id}
              type="number"
              inputMode="decimal"
              min={0}
              step={0.1}
              value={range.end}
              onChange={(e) => onChange({ ...range, end: e.target.value })}
            />
            <button
              type="button"
              className="wm-btn wm-btn--secondary"
              onClick={() =>
                onChange({
                  ...range,
                  end: String(roundTenth(position.current)),
                })
              }
            >
              Use current time
            </button>
          </div>
        )}
      </Field>
      <div className="wm-row wm-row--between">
        <p className="wm-muted">
          {Number.isFinite(len) && len > 0
            ? `Length ${roundTenth(len).toFixed(1)} s`
            : "Length -"}
        </p>
        {canRemove ? (
          <button
            type="button"
            className="wm-btn wm-btn--secondary"
            onClick={onRemove}
          >
            Remove range
          </button>
        ) : null}
      </div>
    </div>
  );
}

function fieldProblems(e: unknown): {
  behavior?: string;
  situation?: string;
  evidence?: string;
} {
  if (!isApiError(e) || e.code !== "validation_error") return {};
  const out: { behavior?: string; situation?: string; evidence?: string } = {};
  for (const f of e.details.fields ?? []) {
    if (f.path.includes("behavior")) {
      out.behavior = String(f.problem).includes("line")
        ? "Use one line."
        : BEHAVIOR_TEXT;
    } else if (f.path.includes("situation")) {
      out.situation = "Choose a situation.";
    } else if (f.path.includes("evidence")) {
      out.evidence = String(f.problem).includes("required")
        ? "Add a clip range. A fact seen in a clip, or said in narration, needs one."
        : EVIDENCE_TEXT;
    }
  }
  return out;
}

const SHARED_ERRORS: ErrorTable = {
  clip_not_ready: CLIP_NOT_READY,
  evidence_out_of_range: EVIDENCE_TEXT,
};

// ------------------------------------------------------------------ edit

export function EditFactSheet({
  fact,
  clips,
  onClose,
  onSaved,
  onReload,
}: {
  fact: Fact;
  /** Ready clips the member may cite. */
  clips: Clip[];
  onClose: () => void;
  onSaved: () => void;
  onReload: () => void;
}) {
  const api = useApi();
  const toast = useToast();
  const original: RangeDraft[] = fact.evidence.map((e) => ({
    key: e.id,
    id: e.id,
    clipId: e.clip_id,
    start: String(e.start_s),
    end: String(e.end_s),
  }));
  const [situation, setSituation] = useState<Situation | "">(fact.situation);
  const [behavior, setBehavior] = useState(fact.behavior);
  const [ranges, setRanges] = useState<RangeDraft[]>(original);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);
  const [checked, setChecked] = useState(false);

  const hasRanges = fact.source !== "staff_note" && fact.evidence.length > 0;
  const rangesChanged =
    ranges.length !== original.length ||
    ranges.some((r, i) => {
      const o = original[i];
      return (
        !o ||
        r.clipId !== o.clipId ||
        num(r.start) !== num(o.start) ||
        num(r.end) !== num(o.end)
      );
    });
  const changed =
    situation !== fact.situation ||
    behavior !== fact.behavior ||
    (hasRanges && rangesChanged);

  const behaviorError = checked ? behaviorProblem(behavior) : null;
  const rangeErrors =
    hasRanges && checked
      ? ranges.map((r) => rangeProblem(r, clips))
      : ranges.map(() => null);
  const server = fieldProblems(failure);

  const save = async () => {
    setChecked(true);
    setFailure(null);
    if (
      !situation ||
      behaviorProblem(behavior) ||
      (hasRanges && ranges.some((r) => rangeProblem(r, clips)))
    )
      return;
    const patch: {
      situation?: Situation;
      behavior?: string;
      evidence?: EvidenceInput[];
    } = {};
    if (situation !== fact.situation) patch.situation = situation;
    if (behavior !== fact.behavior) patch.behavior = behavior.trim();
    if (hasRanges && rangesChanged) {
      patch.evidence = ranges.map((r, i) => {
        const o = original.find((x) => x.id === r.id) ?? original[i];
        const same =
          o &&
          r.id !== undefined &&
          r.clipId === o.clipId &&
          num(r.start) === num(o.start) &&
          num(r.end) === num(o.end);
        return {
          ...(same ? { id: r.id } : {}),
          clip_id: r.clipId,
          start_s: num(r.start),
          end_s: num(r.end),
        };
      });
    }
    setBusy(true);
    try {
      await api.updateFact(fact.id, patch);
      toast.success(
        fact.status === "confirmed"
          ? "Fact saved and set back to draft."
          : "Fact saved.",
      );
      onSaved();
      onClose();
    } catch (e) {
      setFailure(e);
      if (
        isApiError(e) &&
        (e.code === "not_found" || e.code === "invalid_state")
      )
        onReload();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog title="Edit fact" variant="sheet" onClose={onClose} busy={busy}>
      <div className="wm-stack">
        <SituationSelect
          value={situation}
          onChange={setSituation}
          error={
            checked && !situation
              ? "Choose a situation."
              : (server.situation ?? null)
          }
        />
        <BehaviorField
          value={behavior}
          onChange={setBehavior}
          error={behaviorError ?? server.behavior ?? null}
        />

        {hasRanges ? (
          <section aria-labelledby="edit-ranges-h" className="wm-stack">
            <h3 id="edit-ranges-h">{`Clip ranges (${ranges.length} of ${MAX_RANGES})`}</h3>
            {server.evidence ? (
              <p className="wm-error-text">{server.evidence}</p>
            ) : null}
            {ranges.map((r, i) => (
              <RangeRow
                key={r.key}
                range={r}
                clips={clips}
                error={rangeErrors[i] ?? null}
                canRemove={ranges.length > 1}
                onChange={(next) =>
                  setRanges((all) =>
                    all.map((x) => (x.key === r.key ? next : x)),
                  )
                }
                onRemove={() =>
                  setRanges((all) => all.filter((x) => x.key !== r.key))
                }
              />
            ))}
            {ranges.length < MAX_RANGES ? (
              <button
                type="button"
                className="wm-btn wm-btn--secondary"
                onClick={() =>
                  setRanges((all) => [
                    ...all,
                    {
                      key: nextKey(),
                      clipId: all[all.length - 1]?.clipId ?? clips[0]?.id ?? "",
                      start: "0",
                      end: "10",
                    },
                  ])
                }
              >
                Add another range
              </button>
            ) : null}
          </section>
        ) : null}

        <div className="wm-notice wm-notice--warn">
          <p>
            {fact.status === "confirmed"
              ? "Saving sets this fact back to draft. It leaves the public profile until you confirm it again."
              : "Saving clears the watch progress for changed ranges. You must watch them again."}
          </p>
        </div>

        {failure && !Object.keys(server).length ? (
          <ErrorNotice
            error={failure}
            table={{
              ...SHARED_ERRORS,
              not_found: "This fact no longer exists. The list will reload.",
              not_own_session:
                "You can edit only facts from your own sessions.",
              invalid_state:
                "This fact cannot be edited now. It may be deleted. The list will reload.",
            }}
          />
        ) : null}

        <button
          type="button"
          className="wm-btn"
          aria-disabled={!changed || busy ? "true" : undefined}
          onClick={() => {
            if (changed && !busy) void save();
          }}
        >
          {busy ? "Saving..." : "Save changes"}
        </button>
      </div>
    </Dialog>
  );
}

// ------------------------------------------------------------------- add

export function AddFactSheet({
  dogId,
  clips,
  initialClipId,
  onClose,
  onAdded,
}: {
  dogId: string;
  /** Ready clips the member may cite. */
  clips: Clip[];
  initialClipId?: string;
  onClose: () => void;
  onAdded: () => void;
}) {
  const api = useApi();
  const toast = useToast();
  const today = todayLocal();
  const [situation, setSituation] = useState<Situation | "">("");
  const [behavior, setBehavior] = useState("");
  const [attach, setAttach] = useState(initialClipId !== undefined);
  const [range, setRange] = useState<RangeDraft>(() => {
    const first = clips.find((c) => c.id === initialClipId);
    return {
      key: "add",
      clipId: first?.id ?? "",
      start: "0",
      end: first ? String(Math.min(10, Math.floor(first.duration_s))) : "10",
    };
  });
  const [date, setDate] = useState(today);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);
  const [checked, setChecked] = useState(false);

  const server = fieldProblems(failure);
  const rangeError = attach && checked ? rangeProblem(range, clips) : null;

  const submit = async () => {
    setChecked(true);
    setFailure(null);
    if (
      !situation ||
      behaviorProblem(behavior) ||
      (attach && rangeProblem(range, clips))
    )
      return;
    setBusy(true);
    try {
      await api.addFact(dogId, {
        situation,
        behavior: behavior.trim(),
        ...(attach
          ? {
              evidence: [
                {
                  clip_id: range.clipId,
                  start_s: num(range.start),
                  end_s: num(range.end),
                },
              ],
            }
          : { observed_on: date }),
      });
      toast.success(
        attach
          ? "Fact added. Watch the range, then confirm it."
          : "Staff note added.",
      );
      onAdded();
      onClose();
    } catch (e) {
      setFailure(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      title="Add a fact by hand"
      variant="sheet"
      onClose={onClose}
      busy={busy}
    >
      <div className="wm-stack">
        <SituationSelect
          value={situation}
          onChange={setSituation}
          error={
            checked && !situation
              ? "Choose a situation."
              : (server.situation ?? null)
          }
        />
        <BehaviorField
          value={behavior}
          onChange={setBehavior}
          error={
            checked
              ? (behaviorProblem(behavior) ?? server.behavior ?? null)
              : (server.behavior ?? null)
          }
        />
        <div className="wm-check">
          <input
            id="add-attach"
            type="checkbox"
            checked={attach}
            disabled={clips.length === 0}
            onChange={(e) => setAttach(e.target.checked)}
          />
          <label htmlFor="add-attach">Attach a clip range</label>
        </div>
        {clips.length === 0 ? (
          <p className="wm-muted">
            No ready clips yet. You can add a staff note.
          </p>
        ) : null}

        {attach ? (
          <RangeRow
            range={range}
            clips={clips}
            error={rangeError}
            canRemove={false}
            onChange={setRange}
            onRemove={() => undefined}
          />
        ) : (
          <Field label="Date observed">
            {({ id }) => (
              <input
                id={id}
                type="date"
                max={today}
                value={date}
                onChange={(e) => setDate(e.target.value)}
              />
            )}
          </Field>
        )}

        <p>
          {attach
            ? "This will be saved as: Seen in clip. You must watch the range and confirm it."
            : "This will be saved as: Shelter staff note. No clip. Only staff can confirm it."}
        </p>

        {failure ? (
          <ErrorNotice
            error={failure}
            table={{
              ...SHARED_ERRORS,
              consent_required: "Accept the consent notice to add facts.",
              not_found: "This dog was not found. It may have been deleted.",
              not_own_session:
                "You can cite only clips from your own sessions.",
            }}
          />
        ) : null}

        <button
          type="button"
          className="wm-btn"
          disabled={busy}
          onClick={() => void submit()}
        >
          {busy ? "Adding..." : "Add fact"}
        </button>
      </div>
    </Dialog>
  );
}
