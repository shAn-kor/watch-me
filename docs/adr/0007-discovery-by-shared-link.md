# ADR-0007: Discovery by shared link; no search or browse screen in R1

- Status: Accepted
- Date: 2026-10-28

## Context

- SERVICE.md section 11 (decided 2026-10-28): no search or browse at first; shelters share profile links on social media and existing listing sites; adopters arrive by link.
- National portals and apps already aggregate listings (animal.go.kr, Petfinder, Adopt-a-Pet, Pawinhand) (research section 3).
- Export to listing sites is P2; which sites have APIs is unverified (SERVICE.md section 13).

## Decision

- Public profile lives at `/d/{slug}` with no sign-in. No search, no browse (PRD non-goal).
- Unpublished or adopted returns "not available" (REV-5).

## Alternatives considered

- Own search and browse: rejected, would compete with existing aggregators and needs a supply of profiles R1 does not have.
- Export to listing sites: P2, API availability unverified.

## Consequences

- Positive: minimal scope; the hackathon build is one profile page.
- Negative: no organic discovery; traffic depends on shelters sharing links.

## Resolved issues

- Resolved (PRD v1.2): unpublished, adopted, deleted, and unknown slugs all return `404 not_found` with the same body; the frontend shows "not available" (API spec A19).

## Related

PRD section 2, REV-5; ADR-0006, ADR-0008.
