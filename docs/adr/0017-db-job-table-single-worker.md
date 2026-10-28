# ADR-0017: DB-backed job table with one worker process

- Status: Accepted
- Date: 2026-10-28

## Context

- DESIGN section 1: "No Redis; enough for R1 volume."
- The api must not run ffmpeg or long AI calls (DESIGN section 2). Processing target: under 5 minutes per session of up to 3 clips (NFR-1, to be measured).
- Pipeline steps: transcode, transcribe, sample, draft, check; the session merge waits for all clips (DESIGN section 3).

## Decision

- A `job` table (type, payload, status, attempts, error, run_after). One worker process polls it and runs one pipeline step per job.
- Retry rule: transient errors (network, timeout, HTTP 429/5xx) are retried by the job table up to `max_attempts`; schema-invalid AI output is retried once inside the adapter, then fails at once as `ai_invalid_output`. A failed step sets `clip.status = failed` with a cause code (`unsupported_file`, `too_long`, `transcode_failed`, `ai_failed`, `ai_invalid_output`) (CAP-8; data model 3.3).
- The session lifecycle and the `merge` job are in ADR-0035.
- Q&A runs inline in the api: one short model call.
- Deleting files that fail leaves a retry job (DESIGN section 5).

## Alternatives considered

- Redis + Celery (or similar): rejected, extra service, not needed for R1 volume.
- Run steps inside the api request: rejected, long calls.

## Consequences

- Positive: no extra infra; job state is queryable and testable.
- Negative: polling latency; single worker means sessions queue; no horizontal scale.

## Resolved issues

- Resolved (project lead, 2026-10-28): an AI call with schema-invalid output is retried once inside the adapter (validation error appended). If it is still invalid, the job fails at once with `ai_invalid_output`; there is no job-level retry. Job-level retries (`max_attempts`, backoff) apply only to transient errors: network, timeout, HTTP 429 and 5xx. This caps a draft at two model calls per attempt and removes the up-to-four-attempts case.

## Related

PRD CAP-8, NFR-1; ADR-0042 (typed retryable contract); ADR-0016, ADR-0019, ADR-0030.
