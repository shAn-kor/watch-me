# ADR-0015: React + Vite + TypeScript SPA, mobile-first

- Status: Accepted
- Date: 2026-10-28

## Context

- DESIGN section 1: "Two screen sets (creator, public); simple static build."
- Mobile web on current iOS Safari and Android Chrome is the R1 device target (NFR-3). No native app (PRD non-goal).
- The creator flow needs inline range playback and a player that posts playback events (DESIGN section 8).

## Decision

- React + Vite + TypeScript SPA, mobile-first. Creator screens under `/app/...`; public profile at `/d/{slug}`.
- The api serves the static build (no separate frontend host).

## Alternatives considered

- Server-rendered pages / Next.js: not evaluated in the inputs (unverified). Public pages rely on JS for range playback anyway.
- Native app: rejected, mobile web only (PRD section 2).

## Consequences

- Positive: simple static build; one container.
- Negative: SPA sharing links may have weak link previews on social media (inference, unverified); the plan relies on shared links (ADR-0007).
- Follow-up: UI checked on a phone viewport (DESIGN section 11).

## Related

PRD NFR-3; DESIGN sections 8, 11; ADR-0007, ADR-0031.
