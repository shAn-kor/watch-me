# ADR-0026: Serve media with Starlette FileResponse and HTTP Range

- Status: Accepted
- Date: 2026-10-28

## Context

- Range playback must work on iOS Safari and Android Chrome (CAP-9). Fact playback jumps to a time inside a clip (PUB-3).
- Checked 2026-10-28: Starlette 1.10.0 (FastAPI 0.162.0) `FileResponse` answers `Range: bytes=100-199` with 206 and `Content-Range` (DESIGN section 6).
- Unpublished dogs' clips must stay private (NFR-5).

## Decision

- Use `FileResponse` as is at `GET /media/{clip_id}.mp4`; pin `starlette>=1.10`.
- Access: public only for clips cited by a confirmed fact of a published dog; a signed-in member of the org may view its own clips; everything else returns 404 (ADR-0036). Responses use `private, no-cache` with ETag so unpublish and delete take effect at once.
- Playback files are H.264/AAC MP4 produced by the transcode step (ADR-0030); originals are never served.

## Alternatives considered

- Custom Range handler: rejected, not needed once the version is verified.
- Object-store signed URLs (R2/S3): only in the fallback hosting plan (ADR-0027).

## Consequences

- Positive: no custom code for seeking.
- Negative: the api process serves large files; 10 TB/month outbound on the chosen host (ADR-0027).

## Resolved issues

- Resolved (API spec A8, ADR-0036): public media is served only for clips cited by a confirmed fact of a published dog. Extra footage and rejected moments stay private; denials return 404.
- Accepted for R1 (ADR-0043): the whole file of a cited clip is public; the player plays only the cited range.
- Still unverified: real iOS Safari behavior with this endpoint (only the Range response was verified).

## Related

PRD CAP-9, PUB-3, NFR-5; ADR-0018, ADR-0030.
