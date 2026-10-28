import type { ErrorCode, ErrorDetails } from "./types";

/** Error raised by ApiClient for every non-2xx envelope (01 section 1.1). */
export class ApiError extends Error {
  readonly code: ErrorCode;
  readonly status: number;
  readonly details: ErrorDetails;
  /** Seconds from the `Retry-After` header; null when absent. */
  readonly retryAfter: number | null;

  constructor(
    code: ErrorCode,
    status: number,
    details: ErrorDetails = {},
    retryAfter: number | null = null,
    message?: string,
  ) {
    super(message ?? code);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
    this.retryAfter = retryAfter;
  }
}

export function isApiError(e: unknown): e is ApiError {
  return e instanceof ApiError;
}
