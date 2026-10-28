import {
  useEffect,
  useId,
  useRef,
  type KeyboardEvent,
  type ReactNode,
} from "react";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), video, [tabindex]:not([tabindex="-1"])';

interface Props {
  title: string;
  onClose: () => void;
  children: ReactNode;
  /** `sheet` is the bottom sheet with a Close button; `dialog` has its own buttons. */
  variant?: "dialog" | "sheet";
  /** Block Esc while a request runs. */
  busy?: boolean;
}

/**
 * Modal with a focus trap. Esc closes it, focus starts on `[data-autofocus]`
 * (the Cancel button in destructive dialogs) and returns to the opener (05 2.5).
 */
export function Dialog({
  title,
  onClose,
  children,
  variant = "dialog",
  busy = false,
}: Props) {
  const titleId = useId();
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const root = box.current;
    if (root) {
      const first =
        root.querySelector<HTMLElement>("[data-autofocus]") ??
        root.querySelector<HTMLElement>(FOCUSABLE) ??
        root;
      first.focus();
    }
    return () => {
      if (
        opener &&
        typeof opener.focus === "function" &&
        document.contains(opener)
      )
        opener.focus();
    };
  }, []);

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      if (!busy) onClose();
      return;
    }
    if (e.key !== "Tab") return;
    const root = box.current;
    if (!root) return;
    const items = Array.from(
      root.querySelectorAll<HTMLElement>(FOCUSABLE),
    ).filter((el) => !el.hasAttribute("hidden"));
    if (items.length === 0) {
      e.preventDefault();
      return;
    }
    const firstEl = items[0]!;
    const lastEl = items[items.length - 1]!;
    const active = document.activeElement;
    if (e.shiftKey && (active === firstEl || active === root)) {
      e.preventDefault();
      lastEl.focus();
    } else if (!e.shiftKey && active === lastEl) {
      e.preventDefault();
      firstEl.focus();
    }
  };

  return (
    <div className="wm-overlay">
      <div
        ref={box}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={`wm-dialog wm-dialog--${variant}`}
        onKeyDown={onKeyDown}
      >
        <div className="wm-dialog__head">
          <h2 id={titleId} className="wm-dialog__title">
            {title}
          </h2>
          {variant === "sheet" ? (
            <button
              type="button"
              className="wm-btn wm-btn--secondary"
              onClick={onClose}
              disabled={busy}
            >
              Close
            </button>
          ) : null}
        </div>
        {children}
      </div>
    </div>
  );
}

/** Confirm dialog with the Cancel button focused first. */
export function ConfirmDialog({
  title,
  confirmLabel,
  danger = false,
  busy = false,
  confirmDisabled = false,
  cancelLabel = "Cancel",
  onConfirm,
  onCancel,
  children,
}: {
  title: string;
  confirmLabel: string;
  danger?: boolean;
  busy?: boolean;
  confirmDisabled?: boolean;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  children: ReactNode;
}) {
  return (
    <Dialog title={title} onClose={onCancel} busy={busy}>
      <div className="wm-stack">{children}</div>
      <div className="wm-row wm-row--end">
        <button
          type="button"
          className="wm-btn wm-btn--secondary"
          onClick={onCancel}
          data-autofocus
          disabled={busy}
        >
          {cancelLabel}
        </button>
        <button
          type="button"
          className={`wm-btn ${danger ? "wm-btn--danger-fill" : ""}`}
          onClick={onConfirm}
          disabled={busy || confirmDisabled}
          aria-busy={busy}
        >
          {confirmLabel}
        </button>
      </div>
    </Dialog>
  );
}
