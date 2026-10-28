# ADR-0008: Adopted dogs are hidden and clips kept; delete removes files

- Status: Accepted
- Date: 2026-10-28

## Context

- SERVICE.md section 11 (decided 2026-10-28): staff marks the dog "adopted"; the public profile stops showing; the shelter keeps the clips.
- Clips may show volunteers' faces and voices; privacy requires real deletion (PRD NFR-5, NFR-8).
- Returns after adoption are 7-20% (estimate range from a review, research 1.2); keeping clips may help a re-listing (inference, unverified).

## Decision

- Staff actions (REV-6): unpublish; mark adopted (profile hidden, clips kept); delete (clips and facts removed from storage).
- Adopted or deleted dogs are never public (NFR-5).
- Deleting a dog writes a tombstone first, then removes files from Storage, then rows; a failed file delete leaves a retry job (ADR-0038).

## Alternatives considered

- Keep the public profile after adoption as a success story: rejected in the decided plan; not detailed in the inputs.
- Delete on adoption: rejected, the shelter keeps the clips.

## Consequences

- Positive: shelters keep evidence; deletion is a real control for privacy.
- Negative: kept clips continue to occupy storage on a 200 GB free volume (ADR-0027).
- Follow-up: define retention for kept clips (not in the inputs).

## Resolved issues

- Resolved (data model D12, ADR-0038): deleting a dog first writes a tombstone (`status='deleted'`, slug cleared, profile and media return 404), then deletes files by prefix, verifies, then deletes rows. The tombstone is transient and lives until the purge job finishes.

## Related

PRD REV-6, NFR-5, NFR-8; ADR-0018, ADR-0027.
