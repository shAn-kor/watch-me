# ADR-0020: Timestamp strategy: labeled frames by default, 10 s segments as fallback, native video optional

- Status: Accepted
- Date: 2026-10-28

## Context

- Every fact needs a clip range (PRD G2, AI-2). Accuracy of cited ranges is the product's core risk (PRD section 9).
- Checked 2026-10-28 (dev.meta.ai/docs/video-understanding): MP4 only; part `{"type":"video_url","video_url":{"url":..., "fps":n}}`; inline up to 50 MB, Files API up to 1 GiB; audio is read with the frames. Timestamp output or temporal grounding is not documented (DESIGN 3.1).
- Max video duration for Muse Spark is not documented (DESIGN section 13).

## Decision

Three modes, selected by config after the day-1 spike (ADR-0029):

- `frames` (default): sampled frames labeled "t=42s" plus the transcript with times; the model must cite times in its input; the server snaps ranges to the k-second grid and clamps to clip duration. Works with any vision model.
- `segments` (fallback): the model cites segment IDs (e.g. "clip2-seg4"); the server maps an ID to its 10 s range.
- `native_video` (optional): used only if the spike shows better accuracy.

## Alternatives considered

- Native video as default: rejected, no documented timestamp output.
- Free-form times without a grid: rejected, no snapping or validation (inferred).
- Word-level alignment: Voice Transcribe gives turn-level times only (ADR-0024).

## Consequences

- Positive: works with any vision model; the fallback is already designed.
- Negative: time resolution is limited to k seconds (3 s for a 2-minute clip); segments are coarse at 10 s.
- Follow-up: record the spike result and the chosen mode in config.

## Related

PRD AI-2; DESIGN 3.1; ADR-0004, ADR-0021, ADR-0029.
