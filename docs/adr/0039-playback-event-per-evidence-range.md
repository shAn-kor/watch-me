# ADR-0039: One playback event per evidence range, snapshotted

- Status: Accepted
- Date: 2026-10-28

## Context

- DESIGN v0.1 had `playback_event(fact_id, member_id, completed_at)`: one event per fact (ADR-0004).
- A fact may cite several evidence ranges. One event cannot show that every range was played.
- A reviewer can edit a fact's range after playing it. The old playback would then approve a range nobody watched.

## Decision

- `playback_event` rows are keyed by `evidence_id`: `UNIQUE(evidence_id, member_id)`, upserted. Each row snapshots `start_s`, `end_s`, and reports `watched_s`.
- `POST /api/facts/{id}/playback-complete` takes `evidence_id`, `position_s`, `watched_s`; the server applies sanity thresholds.
- Confirm needs a matching event by the confirming member for every evidence range of the fact, and the snapshot must equal the current range.
- Editing or replacing an evidence row deletes its events (FK cascade), so old playback cannot approve a new range. Editing a confirmed fact's evidence returns it to `draft`.
- The event is client-reported and can be forged. This is an accepted risk (ADR-0004): the gate is a review nudge; staff publish and the confirm-without-edit metric are the backstops.

## Alternatives considered

- One event per fact (v0.1): rejected, misses multi-range facts and edits.
- Server-side proof of playback (HTTP Range logs): rejected for R1, seeking and caching make it unreliable and it adds complexity.
- No gate: rejected, ADR-0004.

## Consequences

- Positive: every cited range is played before confirm; edits invalidate stale playback.
- Negative: more events per fact; the review screen tracks per-range progress.

## Related

PRD REV-2, REV-10; API spec 5.8, A18; data model 2.10, D5; ADR-0004, ADR-0005.
