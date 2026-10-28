# ADR-0036: Public media only for clips cited by a confirmed fact

- Status: Accepted
- Date: 2026-10-28

## Context

- DESIGN v0.1 served `GET /media/{clip_id}.mp4` for any clip of a published dog. ADR-0026 flagged that this exposes clips with no confirmed fact.
- A session can hold extra footage, rejected moments, or footage with a third party that no fact cites. Privacy and safety need the public to see only what a human confirmed (PRD NFR-5, ADR-0032).
- Resolved by API spec A8 and the data model.

## Decision

- A clip, its VTT captions (`/media/{clip_id}.vtt`), and its playback file are public only when the dog is `published` and at least one `confirmed` fact cites the clip through `fact_evidence`.
- A signed-in member of the owning org may fetch their own clips in any state.
- Every denial returns `404`, with the same body as an unknown id.
- Responses use `private, no-cache` with ETag, so unpublish, delete, and unconfirm take effect at once.
- Coverage (`filmed_s` vs `confirmed_s`) shows the adopter how much footage exists without exposing uncited footage.

## Alternatives considered

- Serve every clip of a published dog: rejected, exposes uncited footage.
- Signed, expiring URLs: not needed on one host; cost is a revalidation per load (A9).
- Strip uncited clips at publish: rejected, a later confirm should expose the clip with no extra step.

## Consequences

- Positive: the public sees exactly the confirmed evidence; deleting or unconfirming a fact hides its clip.
- Negative: each media request needs an authorization query; `no-cache` costs revalidation on every load.

## Resolved issues

- Accepted for R1 (ADR-0043): a cited clip is served as a whole file; the player plays only the cited range.

## Related

PRD PUB-3, NFR-5; API spec A8, A9; ADR-0004, ADR-0026, ADR-0032.
