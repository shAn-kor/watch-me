# ADR-0030: ffmpeg transcode to H.264 MP4 and fixed clip limits

- Status: Accepted (added: decision found in PRD/DESIGN, not in the original list)
- Date: 2026-10-28

## Context

- Creators film on phones, including iPhone HEVC (CAP-4). Range playback must work on iOS Safari and Android Chrome (CAP-9).
- The audio must be extracted for ASR: WAV mono 16-bit 16 or 24 kHz only (ADR-0024).
- Frames must be sampled for the model (ADR-0021).

## Decision

- Accept MP4/MOV including HEVC; up to 2 minutes and 200 MB per clip; up to 3 clips per session in R1 (CAP-4).
- Pipeline step 1 `transcode`: ffmpeg to H.264/AAC MP4 (`clip.playback_path`), extract 16 kHz mono 16-bit WAV, probe duration (`clip.duration_s`).
- Upload is checked by extension and ffprobe before saving; files get random names; originals are never served (DESIGN section 9).
- Errors surface a cause and a retry, with no silent failure (CAP-8).
- Resumable upload is R2 (CAP-5).

## Alternatives considered

- Serve originals: rejected, HEVC plays poorly on some browsers (inference; not stated in the inputs) and breaks privacy rules.
- Client-side transcode: not discussed in the inputs.
- Longer clips: the 2-minute limit also bounds frame count and model cost (ADR-0021).

## Consequences

- Positive: one playback format; consistent frames and audio for the models.
- Negative: transcode time counts against NFR-1 (under 5 minutes per session, unmeasured); weak connections can fail a 200 MB upload until CAP-5.
- Follow-up: pipeline test with real ffmpeg on two small fixtures (MOV HEVC, MP4).

## Related

PRD CAP-4, CAP-5, CAP-8, CAP-9, NFR-1; ADR-0017, ADR-0021, ADR-0024, ADR-0026.
