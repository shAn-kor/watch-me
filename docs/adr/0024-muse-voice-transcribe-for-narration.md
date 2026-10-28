# ADR-0024: Muse Voice Transcribe for narration in the build; local Whisper for development

- Status: Accepted
- Date: 2026-10-28

## Context

- PRD AI-1: transcribe narration with timestamps using Muse Voice Transcribe; Korean and English both work (acceptance).
- Facts (checked 2026-10-28, DESIGN sections 4 and 15): multipart `POST /v1/asr/transcribe`, model `muse-voice-transcribe-1.0`, mode `ENDPOINTING` (turn `startMs`/`endMs`; no word timestamps); WAV mono 16-bit 16/24 kHz only; 10 minutes and 32 MB per request; Korean and English; $0.18 per audio hour. Not OpenAI-compatible.
- Muse Spark 1.3 audio quality: docs suggest 1.2 for audio (DESIGN section 13).
- Narration-only facts exist: "said by volunteer, not in clip".

## Decision

- Adapter `muse_transcribe` for the judged build; `local_whisper` (faster-whisper, CPU) for development.
- Pipeline step 1 extracts 16 kHz mono 16-bit WAV with ffmpeg; clips are at most 2 minutes, within the 10-minute limit.
- Captions for accessibility come from the transcript (NFR-6).

## Alternatives considered

- Whisper in the judged build: the product uses Muse models in the build for judging (DESIGN section 1); no further reason recorded.
- Let Spark process audio from video: the audio track is read with frames, but the quality note suggests 1.2 for audio; not chosen for transcripts.

## Consequences

- Positive: very low ASR cost per listing ($0.18/hour).
- Negative: turn-level timestamps only; no word-level alignment; a separate non-compatible adapter.

## Open issues

- Quality of Korean transcription of dog-related speech is unmeasured (unverified).

## Related

PRD AI-1, NFR-6; ADR-0009, ADR-0019, ADR-0020, ADR-0030.
