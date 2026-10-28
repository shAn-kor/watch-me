import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { isApiError, type ApiError } from "../../api/errors";
import type { ErrorCode } from "../../api/types";
import { waitText } from "./format";

export type ErrorTable = Partial<Record<ErrorCode, string | ((e: ApiError) => string)>>;

export interface ErrorInfo {
  text: string;
  code: ErrorCode | null;
  /** The text should be followed by the "Open consent notice" link. */
  consentLink: boolean;
  /** Server code is a plain network failure (no response). */
  network: boolean;
}

function idSentence(e: ApiError): string {
  const id = e.details.request_id;
  return typeof id === "string" && id ? ` If it keeps happening, send this ID to the team: ${id}.` : "";
}

/** Global texts of 05 section 2.3. */
export function globalText(e: unknown): string {
  if (!isApiError(e)) return "No connection. Check your network and try again.";
  switch (e.code) {
    case "unauthenticated":
      return "Your session ended. Sign in again.";
    case "csrf_failed":
      return "Your session is out of date. Reload the page and try again.";
    case "rate_limited":
      return `Too many requests. ${waitText(e.retryAfter)}`;
    case "internal_error":
      return `Something went wrong on our side. Try again.${idSentence(e)}`;
    case "malformed_request":
    case "unsupported_media_type":
      return `The app sent a request the server could not read. Reload the page.${idSentence(e)}`;
    case "validation_error":
      return "Check the highlighted fields.";
    case "not_found":
      return "This item was not found. It may have been deleted.";
    case "forbidden_role":
      return "Your role cannot do this. Ask staff.";
    case "consent_required":
      return "Accept the consent notice first.";
    case "invalid_state":
      return "That action is not possible right now. Reload the page.";
    default:
      return e.message && e.message !== e.code ? e.message : "Something went wrong.";
  }
}

const KNOWN: ReadonlySet<string> = new Set([
  "unauthenticated",
  "csrf_failed",
  "rate_limited",
  "internal_error",
  "malformed_request",
  "unsupported_media_type",
  "validation_error",
  "not_found",
  "forbidden_role",
  "consent_required",
  "invalid_state",
]);

/** Screen table first, then the global default. */
export function describeError(e: unknown, table: ErrorTable = {}): ErrorInfo {
  if (!isApiError(e)) {
    return { text: globalText(e), code: null, consentLink: false, network: true };
  }
  const own = table[e.code];
  const text = own === undefined ? globalText(e) : typeof own === "function" ? own(e) : own;
  return {
    text,
    code: e.code,
    consentLink: e.code === "consent_required",
    network: false,
  };
}

export function isUnknownCode(e: unknown): boolean {
  return isApiError(e) && !KNOWN.has(e.code);
}

export interface ErrorNoticeProps {
  error: unknown;
  table?: ErrorTable;
  onRetry?: () => void;
  /** Add the "Back to dogs" link (not found cases). */
  backLink?: boolean;
  children?: ReactNode;
}

/** `ErrorBlock` of 05 section 3: message, optional retry, `role="alert"`. */
export function ErrorNotice({ error, table, onRetry, backLink, children }: ErrorNoticeProps) {
  const info = describeError(error, table);
  return (
    <div role="alert" className="wm-notice wm-notice--error">
      {isUnknownCode(error) && !table ? <p className="wm-strong">Something went wrong.</p> : null}
      <p>{info.text}</p>
      {info.consentLink ? (
        <p>
          <Link to="/app/consent">Open consent notice</Link>
        </p>
      ) : null}
      {backLink ? (
        <p>
          <Link to="/app/dogs">Back to dogs</Link>
        </p>
      ) : null}
      {children}
      {onRetry ? (
        <button type="button" className="wm-btn" onClick={onRetry}>
          Try again
        </button>
      ) : null}
    </div>
  );
}

/** A plain text notice (no `role="alert"`), same look as the warning box. */
export function Notice({ children, tone = "warn" }: { children: ReactNode; tone?: "warn" | "info" }) {
  return <div className={`wm-notice wm-notice--${tone}`}>{children}</div>;
}
