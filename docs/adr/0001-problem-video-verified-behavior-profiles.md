# ADR-0001: Solve the missing-behavior-evidence problem with video-verified shelter dog profiles

- Status: Accepted
- Date: 2026-10-28

## Context

- Behavior is the top adopter decision factor: 58.9% (305 of 517) at 8 Mid-Atlantic sites (research/adoption-pain-points.md 1.2, PubMed 36324195).
- Korea: 30.1% of non-adopters fear illness or behavior problems; "see the animal in person" (27.1%) and "trust" (21.7%) are the top reasons for choosing a route (research 2.2).
- Descriptions change interest and length of stay (Archer 2025; Nakamura 2019, n = 70,733). 30-second video raises perceived friendliness and trainability (PubMed 27636189; small samples, perception only).
- Artificial photo backgrounds had no effect on clicks (p = .314, 680 participants; Lamb 2021). Photo traits give counterintuitive, observational results (research 1.3, section 4 item 4).
- Korean official listings are terse; 3 of the first 10 entries showed only an ID (one snapshot, anecdotal) (research 2.3).
- IDEAS.md shortlisted "Shelter adoption profile maker" as "app cleans photos and writes the profile". Other shortlist items: grooming preview, dog highlight short-form (risk: generic editors). Rejected: home-alone dog monitor (home-cam hacking concern), lost-dog finder (Petco Love Lost already does it, checked 2026-10-28), AR assembly guide (used once or twice a year).

## Decision

Build "Watch Me!": volunteers film short clips and talk; AI drafts behavior facts, each linked to a timestamped clip range; a human confirms; adopters watch the evidence. The differentiator is that every behavior claim links to a clip moment (SERVICE.md section 4).

## Alternatives considered

- Prettier photos / AI photo cleanup (the original IDEAS.md wording): rejected, no effect shown for AI backgrounds and photo results are mixed.
- Text-only AI bio generator: rejected, no evidence behind claims; it is the gap of shelter-software bios (SERVICE.md section 4).
- Grooming preview, highlight short-form, home-alone monitor, lost-dog finder: rejected for the reasons in IDEAS.md above.

## Consequences

- Positive: grounded in the strongest evidence cluster (descriptions) plus video evidence.
- Negative: filming may cost shelters more time than a text bio; no baseline exists for time per listing (PRD G1 is a hypothesis).
- Negative: whether video increases real adoptions is unverified (research section 4 item 2). Whether a shipping product already does "video to profile" is unverified (research section 3).
- Follow-up: measure volunteer time per listing in R1.

## Open issues

- Unresolved: Best Friends is developing an AI tool, scope unknown (unverified). Still unresolved; monitor.

## Related

PRD section 1, G1-G3; ADR-0002, ADR-0003, ADR-0034.
