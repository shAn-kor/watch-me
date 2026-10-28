# ADR-0004: A human confirms every fact; confirm is enabled only after the clip range plays to the end

- Status: Accepted
- Date: 2026-10-28

## Context

- SERVICE.md section 7: a human (volunteer/staff) confirms every fact before publishing. Best Friends norms: "AI informs, never replaces human judgment"; "AI drafts, you review" (research 1.3).
- Red-team risk: volunteers confirm without watching (PRD section 9).
- AI timestamps may be unreliable (ADR-0020, ADR-0029).

## Decision

- The gate is per evidence range: one `playback_event` per (evidence, member) (ADR-0039). The event is a nudge, not proof (see Resolved issues).
- Every fact is a draft until a member confirms, edits, or deletes it (REV-2). Nothing unconfirmed appears publicly (PUB-2).
- "Confirm" is enabled only after the fact's clip range has played to its end. The client posts `POST /api/facts/{id}/playback-complete`; the server rejects a confirm with no playback event by that member (DESIGN section 6, `playback_event` table).
- Range playback: set `currentTime = start`, play, pause at `end` on `timeupdate`; the event fires once `end` is reached (DESIGN section 8).
- Volunteers confirm only facts from their own sessions (REV-4). REV-10 records whether a fact is AI-unchanged or human-edited.
- Metric: draft acceptance. A very high rate with short review time signals rubber-stamping (PRD section 8).

## Alternatives considered

- Confirm button always enabled: rejected, invites unwatched confirmations.
- Fully automatic publishing: rejected, contradicts the human-review rule.
- Review by sampling: not in the inputs (not considered).

## Consequences

- Positive: every published fact had its evidence played at least once.
- Negative: slower review; REV-10 is first in the PRD cut order, which weakens the rubber-stamping metric.

## Resolved issues

- Resolved (accepted risk, project lead, 2026-10-28): the playback-complete event is client-reported and can be forged. It is a review nudge, not a security control. The server only applies sanity thresholds (`evidence_id`, `position_s`, `watched_s`, API spec A18). The backstops are the staff publish (ADR-0005) and the confirm-without-edit metric (REV-10 draft acceptance), which flags rubber-stamping.

## Related

PRD REV-1, REV-2, REV-4, REV-10, G2; ADR-0005, ADR-0020.
