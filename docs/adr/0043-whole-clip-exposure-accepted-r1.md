# ADR-0043: Whole files of cited clips are public in R1; per-range cutting is R2

- Status: Accepted
- Date: 2026-10-28

## Context

- ADR-0036 makes a clip public when a confirmed fact cites it. The file served is the whole clip, not only the cited range (ADR-0026 serves the file with Range).
- Cutting each range into its own file needs extra ffmpeg work, storage, and deletion handling.

## Decision

- Accepted for R1: anyone with the link can fetch the whole file of a cited clip. The public player plays only the cited range.
- The publish dialog tells staff that visitors can play the whole clip.
- Capture rules (ADR-0032) and the member consent step stay the main control for what is in a clip.
- Per-range clip cutting is R2.

## Alternatives considered

- Cut a file per evidence range in R1: rejected, cost and schedule.
- Signed range-limited URLs: rejected, the file is still fully readable by a client.

## Consequences

- Positive: no new media pipeline; one file per clip.
- Negative: a visitor can see footage outside the cited range of a cited clip; this is a disclosed privacy cost.

## Related

PRD PUB-3, NFR-5; API spec media rules; ADR-0026, ADR-0032, ADR-0036.
