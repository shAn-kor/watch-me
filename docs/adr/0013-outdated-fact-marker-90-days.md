# ADR-0013: Facts older than 90 days show "may be outdated" (R2)

- Status: Accepted (marker is decided; implementation is R2)
- Date: 2026-10-28

## Context

- Dog behavior can change after the observation; returns occur at median 8 days in one study (PubMed 35565480), and 51% of returned dogs came back after more than 60 days (Hawes 2020). Both are indirect support (inferred).
- SERVICE.md section 10 (decided): each fact shows its observation date; facts older than 90 days show "may be outdated"; tune the threshold with shelters.

## Decision

- R1 stores and shows the observation date (`observed_on`, PUB-2).
- PUB-5 (R2): the "may be outdated" marker after 90 days; the threshold is a setting.

## Alternatives considered

- Hide old facts: not chosen; the plan prefers a visible warning.
- No expiry: rejected in the decided plan.
- Other thresholds: only "tune with shelters" is recorded; 90 days has no supporting evidence in the inputs (unverified).

## Consequences

- Positive: honest freshness signal at low cost.
- Negative: 90 days is a guess until shelters weigh in. R1 profiles show the date but no marker.

## Resolved issues

- Resolved: SERVICE.md lists the marker as decided; PRD v1.2 puts it in R2 and SERVICE.md section 6 defers to the PRD. No conflict in intent.

## Related

PRD PUB-5; ADR-0002, ADR-0012.
