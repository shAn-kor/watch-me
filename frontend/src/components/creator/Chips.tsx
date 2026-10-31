import type {
  DogStatus,
  FactOrigin,
  FactStatus,
  SessionStatus,
} from "../../api/types";

type IconName = "check" | "draft" | "adopted";

/** Plain line icons (05 section 8.1), 16 px, decorative: the word carries the meaning. */
function Icon({ name }: { name: IconName }) {
  return (
    <svg
      className="wm-chip__icon"
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {name === "check" ? <path d="M3 8.5l3.5 3.5L13 4.5" /> : null}
      {name === "draft" ? <circle cx="8" cy="8" r="5" /> : null}
      {name === "adopted" ? <path d="M3.5 6h9M3.5 10h9" /> : null}
    </svg>
  );
}

function Chip({
  tone,
  icon,
  children,
}: {
  tone: string;
  icon: IconName;
  children: string;
}) {
  return (
    <span className={`wm-chip wm-chip--${tone}`}>
      <Icon name={icon} /> {children}
    </span>
  );
}

export function DogStatusChip({ status }: { status: DogStatus }) {
  if (status === "published")
    return (
      <Chip tone="ok" icon="check">
        Published
      </Chip>
    );
  if (status === "adopted")
    return (
      <Chip tone="muted" icon="adopted">
        Adopted
      </Chip>
    );
  return (
    <Chip tone="muted" icon="draft">
      Draft
    </Chip>
  );
}

export function FactStatusChip({ status }: { status: FactStatus }) {
  return status === "confirmed" ? (
    <Chip tone="ok" icon="check">
      Confirmed
    </Chip>
  ) : (
    <Chip tone="muted" icon="draft">
      Draft
    </Chip>
  );
}

export const SESSION_STATUS_TEXT: Record<SessionStatus, string> = {
  open: "Open",
  processing: "Processing",
  review: "Ready to review",
  failed: "Failed",
};

export function OriginChip({ origin }: { origin: FactOrigin }) {
  const text =
    origin === "ai_unchanged"
      ? "AI draft"
      : origin === "human_edited"
        ? "Edited"
        : "Added by hand";
  return <span className="wm-chip wm-chip--plain">{text}</span>;
}
