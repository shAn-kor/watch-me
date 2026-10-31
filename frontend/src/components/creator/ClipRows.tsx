import { Link } from "react-router-dom";
import type { Clip, ClipFailCode, ClipStep } from "../../api/types";
import { formatClock } from "../../lib/time";
import type { LocalUpload } from "./uploads";

const STEP_TEXT: Record<ClipStep, string> = {
  transcode: "Converting video",
  transcribe: "Listening to narration",
  sample: "Picking frames",
  draft: "Drafting facts",
};
const STEP_NUMBER: Record<ClipStep, number> = {
  transcode: 1,
  transcribe: 2,
  sample: 3,
  draft: 4,
};

const FAIL_TEXT: Record<ClipFailCode, string> = {
  unsupported_file: "This video format could not be read.",
  too_long: "The clip is longer than 2 minutes.",
  transcode_failed: "We could not convert this clip.",
  ai_failed: "The AI step did not finish.",
  ai_invalid_output: "The AI answer was not usable.",
};

function clipFailText(c: Clip): string {
  if (c.error?.cause) return c.error.cause;
  return c.fail_code
    ? FAIL_TEXT[c.fail_code]
    : "This clip could not be processed.";
}

function clipRetryable(c: Clip): boolean {
  if (c.error) return c.error.retryable;
  return c.fail_code !== "unsupported_file" && c.fail_code !== "too_long";
}

interface ClipRowProps {
  clip: Clip;
  /** Owner or staff: may retry and delete. */
  canAct: boolean;
  /** Delete is also offered on ready clips while the session is open. */
  canDeleteReady: boolean;
  noSound: boolean;
  busy: boolean;
  onWatch: (clip: Clip) => void;
  onRetry: (clip: Clip) => void;
  onDelete: (clip: Clip) => void;
}

export function ClipRow({
  clip,
  canAct,
  canDeleteReady,
  noSound,
  busy,
  onWatch,
  onRetry,
  onDelete,
}: ClipRowProps) {
  const retryable = clipRetryable(clip);
  return (
    <li>
      <p className="wm-clip-line">
        <span className="wm-strong">Clip {clip.ordinal}</span>
        <span className="wm-clip-name" title={clip.original_filename}>
          {clip.original_filename}
        </span>
        {clip.status === "ready" ? (
          <span className="wm-clip-time">{formatClock(clip.duration_s)}</span>
        ) : null}
      </p>
      {clip.status === "uploaded" ? <p>Uploaded. Waiting to start.</p> : null}
      {clip.status === "processing" ? (
        <p>
          {clip.step
            ? `Step ${STEP_NUMBER[clip.step]} of 4: ${STEP_TEXT[clip.step]}`
            : "Processing"}
        </p>
      ) : null}
      {clip.status === "ready" ? (
        <div className="wm-row wm-row--between">
          <p>Ready</p>
          <div className="wm-row">
            <button
              type="button"
              className="wm-btn wm-btn--secondary"
              onClick={() => onWatch(clip)}
            >
              Watch clip
            </button>
            {canAct && canDeleteReady ? (
              <button
                type="button"
                className="wm-btn wm-btn--danger"
                onClick={() => onDelete(clip)}
              >
                Delete clip
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
      {clip.status === "failed" ? (
        <div className="wm-stack">
          <p className="wm-error-text">{clipFailText(clip)}</p>
          {!retryable ? (
            <p>Delete this clip and upload a different file.</p>
          ) : null}
          {canAct ? (
            <div className="wm-row">
              {retryable ? (
                <button
                  type="button"
                  className="wm-btn"
                  disabled={busy}
                  onClick={() => onRetry(clip)}
                >
                  Try again
                </button>
              ) : null}
              <button
                type="button"
                className="wm-btn wm-btn--danger"
                onClick={() => onDelete(clip)}
              >
                Delete clip
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
      {noSound ? (
        <p className="wm-muted">
          This clip has no sound. It will have no narration and no captions.
        </p>
      ) : null}
    </li>
  );
}

export function LocalRow({
  item,
  ordinal,
  onRetry,
  onRemove,
  onCancel,
}: {
  item: LocalUpload;
  ordinal: number;
  onRetry: (key: string) => void;
  onRemove: (key: string) => void;
  onCancel: (key: string) => void;
}) {
  return (
    <li>
      <p className="wm-clip-line">
        <span className="wm-strong">Clip {ordinal}</span>
        <span className="wm-clip-name" title={item.file.name}>
          {item.file.name}
        </span>
      </p>
      {item.state === "waiting" ? <p>Waiting to upload</p> : null}
      {item.state === "uploading" ? (
        <div className="wm-stack">
          <p>Uploading {item.percent}%</p>
          <div
            className="wm-progress"
            role="progressbar"
            aria-label="Upload progress"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={item.percent}
          >
            <div style={{ width: `${item.percent}%` }} />
          </div>
          <div className="wm-row">
            <button
              type="button"
              className="wm-btn wm-btn--secondary"
              onClick={() => onCancel(item.key)}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}
      {item.state === "failed" ? (
        <div className="wm-stack">
          <p className="wm-error-text">{item.error}</p>
          {item.consentLink ? (
            <p>
              <Link to="/app/consent">Open consent notice</Link>
            </p>
          ) : null}
          <div className="wm-row">
            {item.retryable ? (
              <button
                type="button"
                className="wm-btn"
                onClick={() => onRetry(item.key)}
              >
                Try again
              </button>
            ) : null}
            <button
              type="button"
              className="wm-btn wm-btn--secondary"
              onClick={() => onRemove(item.key)}
            >
              Remove
            </button>
          </div>
        </div>
      ) : null}
    </li>
  );
}
