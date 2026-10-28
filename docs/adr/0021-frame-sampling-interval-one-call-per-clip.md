# ADR-0021: Frame interval k = max(1, ceil(duration/48)) and one model call per clip

- Status: Accepted
- Date: 2026-10-28

## Context

- Muse Spark accepts at most 50 images per request; 50 MB inline each; images only in user messages (DESIGN section 15).
- A 2-minute clip at 1 fps is 120 frames and does not fit one request (DESIGN section 3).
- Clips are limited to 2 minutes and 200 MB, 3 clips per session in R1 (CAP-4).

## Decision

- Sample frames every k seconds, k = max(1, ceil(duration/48)), each labeled with its time. A 2-minute clip sends 40 frames (one every 3 s).
- Step 4 runs one model call per clip; results are merged per session after all clips finish steps 1-4.
- Structured output through `response_format` `json_schema` with `strict` set true (recursive schemas are rejected; `strict` defaults to false).

## Alternatives considered

- 1 fps with several calls per clip: rejected in the design, frames do not fit one request; cross-call merging is not designed.
- Fixed number of frames per clip: not discussed in the inputs.

## Consequences

- Positive: bounded cost and latency; always within the 50-image cap (48 frames at most).
- Negative: short behaviors under k seconds can be missed (inference); accuracy is only measured in the spike.

## Open issues

- None found. Check: 120 s / 48 = 2.5, so k = 3 and 40 frames, which matches DESIGN.

## Related

PRD CAP-4, AI-2; DESIGN sections 3, 15; ADR-0020, ADR-0030.
