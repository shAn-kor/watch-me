import { useEffect, useId, useState, type ReactNode } from "react";
import { TopBar } from "./TopBar";

/** Page frame: top bar, content column, optional fixed action bar (05 section 2.1). */
export function Screen({
  title,
  backTo,
  onBack,
  action,
  children,
}: {
  title: string;
  backTo?: string;
  onBack?: () => void;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="wm-page">
      <TopBar title={title} backTo={backTo} onBack={onBack} />
      <div className="wm-content">{children}</div>
      {action ? <div className="wm-actionbar">{action}</div> : null}
    </div>
  );
}

/** Skeleton blocks with a live "Loading..." text; slow loads say so after 10 s (05 section 2.2). */
export function Loading({
  text,
  onRetry,
}: {
  text: string;
  onRetry?: () => void;
}) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setSlow(true), 10_000);
    return () => clearTimeout(t);
  }, []);
  return (
    <div role="status">
      <p>{text}</p>
      <div className="wm-skeleton" aria-hidden="true" />
      <div className="wm-skeleton" aria-hidden="true" />
      {slow ? (
        <>
          <p>This is taking longer than usual.</p>
          {onRetry ? (
            <button type="button" className="wm-btn" onClick={onRetry}>
              Try again
            </button>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

/** Label, input, help and error text tied together with `aria-describedby`. */
export function Field({
  label,
  help,
  error,
  children,
}: {
  label: string;
  help?: string;
  error?: string | null;
  children: (props: {
    id: string;
    describedBy: string | undefined;
    invalid: boolean;
  }) => ReactNode;
}) {
  const id = useId();
  const helpId = `${id}-help`;
  const errId = `${id}-err`;
  const describedBy =
    [help ? helpId : null, error ? errId : null].filter(Boolean).join(" ") ||
    undefined;
  return (
    <div className="wm-field">
      <label htmlFor={id}>{label}</label>
      {children({ id, describedBy, invalid: Boolean(error) })}
      {help ? (
        <p id={helpId} className="wm-help">
          {help}
        </p>
      ) : null}
      {error ? (
        <p id={errId} className="wm-error-text">
          <span className="wm-visually-hidden">Error: </span>
          {error}
        </p>
      ) : null}
    </div>
  );
}

/** Radio group in a fieldset with a legend. */
export function RadioGroup<T extends string>({
  legend,
  name,
  value,
  options,
  error,
  onChange,
}: {
  legend: string;
  name: string;
  value: T | "";
  options: readonly { value: T; label: string }[];
  error?: string | null;
  onChange: (v: T) => void;
}) {
  const id = useId();
  return (
    <div className="wm-field">
      <fieldset aria-describedby={error ? `${id}-err` : undefined}>
        <legend>{legend}</legend>
        <div className="wm-row">
          {options.map((o) => (
            <div key={o.value} className="wm-check">
              <input
                type="radio"
                id={`${id}-${o.value}`}
                name={name}
                value={o.value}
                checked={value === o.value}
                onChange={() => onChange(o.value)}
              />
              <label htmlFor={`${id}-${o.value}`}>{o.label}</label>
            </div>
          ))}
        </div>
      </fieldset>
      {error ? (
        <p id={`${id}-err`} className="wm-error-text">
          <span className="wm-visually-hidden">Error: </span>
          {error}
        </p>
      ) : null}
    </div>
  );
}

/** A button that stays focusable while blocked (`aria-disabled`) and ignores clicks. */
export function BlockedButton({
  blocked,
  onClick,
  describedBy,
  className = "wm-btn",
  children,
}: {
  blocked: boolean;
  onClick: () => void;
  describedBy?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      className={className}
      aria-disabled={blocked ? "true" : undefined}
      aria-describedby={describedBy}
      onClick={() => {
        if (!blocked) onClick();
      }}
    >
      {children}
    </button>
  );
}
