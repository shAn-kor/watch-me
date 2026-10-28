# ADR-0028: Separate git repository `watch-me/` for the public submission

- Status: Accepted
- Date: 2026-10-28

## Context

- The repo layout is rooted at `watch-me/` (DESIGN section 10): `backend/`, `frontend/`, `tools/`, `eval/`, Docker files.
- Planning material (SERVICE.md, IDEAS.md, research/) lives in the parent hackathon folder. `watch-me/docs/` holds PRD.md and DESIGN.md.
- The submission is public. The reason for a separate repository comes from the task brief only; the input documents do not state it (unverified).

## Decision

Keep the product code, PRD, design docs and ADRs in a separate git repository `watch-me/`. Do not mix it with the workspace-level repository.

## Alternatives considered

- Monorepo in the workspace repository: rejected by the task owner; reasons not recorded in the inputs (unverified).
- Subfolder without its own repo: same.

## Consequences

- Positive: the submission contains only product material.
- Negative: research and SERVICE.md live outside the repo; PRD/ADR citations to `research/adoption-pain-points.md` and `SERVICE.md` point outside it.
- Follow-up: before submission, copy or summarize the cited evidence into the repo, and check the public repo has no credentials, real clips, or personal data (only an example env file).

## Related

DESIGN section 10; ADR-0011.
