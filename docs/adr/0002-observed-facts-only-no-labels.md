# ADR-0002: Publish observed facts only; no personality scores or labels; eight-situation taxonomy

- Status: Accepted
- Date: 2026-10-28

## Context

- Short observations do not reliably predict aggression, food guarding, or separation problems (123 dogs, Australia; PubMed 32708444). An AI note from a short video would be weaker than a formal assessment (research 1.2).
- Returning owners had higher expectations for behavior (PubMed 35565480).
- Archer 2025: some words helped (calm, friendly) and "energetic" reduced interest; labels move perception (research 1.3).
- SERVICE.md section 10 (decided 2026-10-28) defines a fact as one observed behavior in one situation; it never states a trait.

## Decision

- A fact has situation, behavior, evidence (clip ranges), source (clip / narration / staff_note), observed_on, status, origin, confirmed_by (PRD 5.1).
- Wording describes what can be checked in the clip ("barked 3 times"). Banned: trait labels and judgments ("aggressive", "friendly", "anxious", "good with kids", "calm dog") and paraphrased trait claims ("doesn't mind being grabbed"). The list lives in config and grows (PRD 5.3).
- Eight situations: meeting a new person; handling; leash walk; meeting another dog; food and toys; alone time; indoors and rest; children or cats (only when observed, never inferred).
- A situation with no clip shows "Not observed yet"; the app never fills the gap. Narration-only facts say "said by volunteer, not in clip".
- Enforced by AI-3: banned-word list plus a model pass that flags trait claims (warning on the review card; the human reviewer is the main guard).

## Alternatives considered

- Personality scores or trait tags: rejected, unreliable from short clips and a safety risk (see above).
- Free-text bios from AI: rejected, claims have no evidence link.
- Fewer or open-ended situations: not documented in the inputs; the fixed eight double as the filming checklist.

## Consequences

- Positive: every claim is checkable; coverage can be computed per situation.
- Negative: the banned list cannot catch every paraphrase; the AI-3 check is explicitly "not a guarantee".
- Follow-up: grow the banned list from review warnings.

## Related

PRD 5.1-5.3, AI-3, PUB-2, PUB-4; SERVICE.md sections 7 and 10; ADR-0003, ADR-0004.
