# ADR-0031: Mobile web only; no native app

- Status: Accepted (added: decision found in PRD/SERVICE.md)
- Date: 2026-10-28

## Context

- Creators are shelter staff, volunteers and fosters who film on their phones (SERVICE.md section 11: "mobile web, no app install").
- Adopters arrive from shared links (ADR-0007).
- Hackathon time is short (due 2026-11-05 11:00 KST).

## Decision

- Mobile web on current iOS Safari and Android Chrome (NFR-3). No native mobile app (PRD non-goal).
- Capture is by browser upload of recorded clips; no in-app camera is specified in the inputs.

## Alternatives considered

- Native app: rejected, install friction for volunteers and extra scope.
- Desktop-first web: rejected, creators film on phones.

## Consequences

- Positive: no install; same code for creators and adopters.
- Negative: browser upload of up to 200 MB on weak connections is fragile (CAP-5 is R2); no background upload.

## Resolved issues

- Resolved (PRD v1.2): capture is upload-only in R1. SERVICE.md "record or upload clips" is the earlier plan; PRD v1.2 wins. In-page recording is not in R1.

## Related

PRD NFR-3, CAP-4, section 2; ADR-0015, ADR-0030.
