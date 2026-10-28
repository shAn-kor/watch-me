# ADR-0044: Merge duplicate facts across clips by joining evidence

- Status: Accepted
- Date: 2026-10-28

## Context

- Each clip is drafted by its own model call (ADR-0021), so two clips can yield the same fact. The first design hard-deleted one duplicate.
- Deleting one fact drops the evidence of the second clip, which the adopter could have played.

## Decision

- The `merge` job treats facts with the same source, same situation, and equal meaning as duplicates (rules in 04-ai-design 5.6).
- The survivor (longer text) takes the union of evidence rows: overlapping or touching ranges join, at most 3 rows, longest first. The other `merged=0` row is removed before anyone sees it.
- A `clip` fact beats a `narration` duplicate; the narration row is removed and no evidence is merged.
- Data model F2 and the merge tests follow this rule.

## Alternatives considered

- Hard delete the loser: rejected, loses evidence.
- Keep both facts: rejected, the profile repeats itself.

## Consequences

- Positive: one fact with the strongest evidence from all clips.
- Negative: more merge logic and tests; the 3-row cap can drop weaker ranges.

## Related

PRD AI-2, REV-1; data model F2, D21; ADR-0021, ADR-0035.
