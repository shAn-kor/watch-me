import type {
  DogStatus,
  FactOrigin,
  FactStatus,
  SessionStatus,
} from "../../api/types";

function Chip({
  tone,
  icon,
  children,
}: {
  tone: string;
  icon: string;
  children: string;
}) {
  return (
    <span className={`wm-chip wm-chip--${tone}`}>
      <span aria-hidden="true">{icon}</span> {children}
    </span>
  );
}

export function DogStatusChip({ status }: { status: DogStatus }) {
  if (status === "published")
    return (
      <Chip tone="ok" icon="+">
        Published
      </Chip>
    );
  if (status === "adopted")
    return (
      <Chip tone="muted" icon="=">
        Adopted
      </Chip>
    );
  return (
    <Chip tone="muted" icon="o">
      Draft
    </Chip>
  );
}

export function FactStatusChip({ status }: { status: FactStatus }) {
  return status === "confirmed" ? (
    <Chip tone="ok" icon="+">
      Confirmed
    </Chip>
  ) : (
    <Chip tone="muted" icon="o">
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
