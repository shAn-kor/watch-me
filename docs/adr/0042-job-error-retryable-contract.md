# ADR-0042: JobError carries a retryable flag; retry only transient errors

- Status: Accepted
- Date: 2026-10-28

## Context

- ADR-0017 set the retry rule in prose. Adapters and handlers need one typed way to say whether the job table should retry.
- Provider errors differ: 429 and 5xx pass with time; 400-class errors (bad key, no credit, bad image) never do, and retrying them spends calls for nothing.

## Decision

- AI adapters and job handlers raise `JobError(code, retryable: bool)`.
- Schema-invalid output: one retry inside the adapter, then `ai_invalid_output`, `retryable=False`.
- Non-transient provider errors (HTTP 400, 401, 402, 403, 404, including image errors): fail at once as `ai_failed`, `retryable=False`, no automatic retry.
- Transient errors (network, timeout, HTTP 429, 5xx; for ffmpeg: timeout, kill, disk full): `retryable=True`; the job table retries up to `max_attempts` with backoff.
- A user can still retry a failed clip by hand (`POST /api/clips/{id}/retry`).

## Alternatives considered

- Retry every error: rejected, wastes credit on permanent failures.
- Decide by code string in the runner: rejected, the flag keeps the rule next to the raise site.

## Consequences

- Positive: predictable cost and a clear failure cause for the member.
- Negative: a provider that returns 400 for a transient fault fails the clip; manual retry covers it.

## Related

PRD CAP-8; ADR-0017 (extends it), ADR-0019, ADR-0033; 04-ai-design error mapping.
