# ADR-0018: Local disk storage behind a `Storage` interface

- Status: Accepted
- Date: 2026-10-28

## Context

- DESIGN section 1: "S3-compatible store later without code changes upstream."
- Clips are private until published; deletion must remove storage copies (NFR-5, NFR-8).
- Fallback hosting serves clips from Cloudflare R2 because GCP e2-micro outbound (1 GB/month) is too small (DESIGN section 14).

## Decision

- Files (originals, playback MP4s, frames, photos) are stored on a local volume through a `Storage` interface (`storage.py`).
- Files get random names; media is never served from the original path (DESIGN section 9).
- A second implementation (S3-compatible, e.g. R2) can plug in for the fallback host.

## Alternatives considered

- S3-compatible storage from day one: rejected for R1; an extra service and account.

## Consequences

- Positive: simple; deletion order (files first, rows second) is easy to enforce.
- Negative: volume capacity is the limit (200 GB block on the chosen host); no CDN.
- Follow-up: implement the R2 adapter only if the fallback host is used.

## Related

PRD NFR-5, NFR-8; ADR-0008, ADR-0026, ADR-0027.
