# ADR-0005: Staff publishes; volunteer-confirmed facts still need a staff publish

- Status: Accepted
- Date: 2026-10-28

## Context

- SERVICE.md section 12 (decided): roles are admin, staff (publishes), volunteer/foster (films and confirms facts they filmed). "Facts a volunteer confirms still need a staff publish, so the shelter owns what is public."
- Foster-based rescues are a large channel and Shelterluv lets fosters edit bios, so the volunteer as author is a real workflow (research 1.3).

## Decision

- Publish, unpublish, mark adopted, delete: staff only (REV-5, REV-6). Staff can also confirm. Volunteers film and confirm only their own sessions (PRD section 3, REV-4).
- Publish is blocked until the REV-9 checklist is done: (a) no people other than consenting members in any clip, (b) known concerns filled in or "none known".
- DESIGN: "Published" is a dog state (`draft/published/adopted/deleted`); a published profile shows facts with status `confirmed`. Publishing does not copy facts.
- R1 has one staff and one volunteer account (seeded).

## Alternatives considered

- Volunteers publish directly: rejected, the shelter must own what is public.
- Org admin role in R1: deferred to R2 (PRD section 3, ORG-3).

## Consequences

- Positive: accountability sits with the shelter; confirmed_by records role.
- Negative: staff become a bottleneck for publishing.

## Resolved issues

- Resolved (PRD v1.2): fact status is `draft / confirmed / deleted`; "published" is a dog state only. The PRD now matches DESIGN.
- Resolved (PRD defers): the admin role is R2 (ORG-3). SERVICE.md is the earlier plan; PRD v1.2 wins.

## Related

PRD REV-4, REV-5, REV-6, REV-9; ADR-0004, ADR-0012.
