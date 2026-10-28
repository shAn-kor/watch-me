# ADR-0003: Position the product as not a behavior or safety assessment

- Status: Accepted
- Date: 2026-10-28

## Context

- Red-team review (PRD v1.1 header) found the risk that adopters read facts as a safety guarantee, with a bite after adoption (PRD section 9).
- Aggression-related behavior is 38.2% of dog returns in Hawes 2020 (102 dogs); short-observation predictions are weak for aggression, guarding, separation (research 1.2).
- Shelters may film only the good moments (PRD section 9).

## Decision

- PUB-0: a fixed banner above the facts on every profile: "These clips are short samples. They are not a behavior or safety assessment. Meet the dog and talk to the shelter before adopting."
- PUB-1/PUB-2: show clip count and total seconds per situation and the clip length per fact (e.g. "1 clip, 9 s").
- PUB-8 / REV-9: a "known concerns" field, shown above the facts, filled in or marked "none known"; publish is blocked otherwise.
- PUB-9: situation 8 (children or cats) facts carry "ask the shelter about an in-person meeting"; only staff can confirm them.
- A short terms page in R1; legal review (US state biometric laws, Korea PIPA) before real launch (NFR-9).
- Non-goals: no health assessment or medical advice (PRD section 2).

## Alternatives considered

- No disclaimer, rely on fact wording: rejected by the red-team finding above.
- Offer a safety or compatibility rating: rejected, contradicts ADR-0002 and the evidence above.
- Allow anyone to confirm situation 8: rejected; the PRD restricts it to staff. Since PRD v1.2 the cut list cannot drop it.

## Consequences

- Positive: clearer liability posture and honest framing.
- Negative: the banner and known-concerns field add friction; sample length is only partly visible.
- Follow-up: legal review before launch (R2).

## Resolved issues

- Resolved (PRD v1.2): the PUB-9 staff-only rule and other safety controls (PUB-0, PUB-8, REV-9, QA-2) are removed from the cut list and are never cut. The Alternatives note about cutting the staff-only rule no longer applies.

## Related

PRD PUB-0, PUB-8, PUB-9, REV-9, NFR-9; ADR-0002, ADR-0004.
