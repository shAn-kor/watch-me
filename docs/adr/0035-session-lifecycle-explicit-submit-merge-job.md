# ADR-0035: Session lifecycle with an explicit submit and a merge job

- Status: Accepted
- Date: 2026-10-28

## Context

- DESIGN v0.1 listed `session.status` without values and said the session merge "waits until every clip has finished steps 1-4" (DESIGN v0.1 section 3). Nothing triggered the merge.
- Volunteers upload clips one by one, up to 3 per session (CAP-4). The server cannot know when the last clip has arrived.
- Unmerged AI output must not appear in review (data model D4).

## Decision

- Session status: `open -> processing -> review`, or `failed` (data model 3.2, S1-S5).
- Uploads are accepted only in `open`. The owner calls `POST /api/sessions/{id}/submit` (at least one live clip) to move to `processing`.
- When every live clip is `ready` or `failed`, a `merge` job runs. It merges per-clip drafts into session facts. `fact.merged` marks facts the merge has processed; unmerged AI drafts are not shown in review.
- `check` (wording flags) runs once per session after the merge, not per clip. When it ends, the session becomes `review`.
- The session becomes `failed` when all live clips fail (`no_usable_clip`) or the merge fails (`merge_failed`). A clip retry moves a `failed` or `review` session back to `processing`; the next merge is idempotent (only `merged=0` facts).

## Alternatives considered

- Merge when the last clip finishes, with no submit: rejected, the server does not know which clip is last.
- A timer after the last upload: rejected, guesses the volunteer's intent and breaks with weak connections.
- Merge per clip with no session merge: rejected, duplicate facts across clips of one session.

## Consequences

- Positive: one clear trigger; review never shows half-merged output; retries are safe.
- Negative: one more user step (submit); a session with a stuck clip waits until that clip is `ready` or `failed`.

## Related

PRD CAP-3, CAP-4, CAP-8, REV-1; API spec 5.4, data model 3.2, D4; ADR-0017, ADR-0021.
