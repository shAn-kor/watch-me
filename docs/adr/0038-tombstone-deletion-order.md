# ADR-0038: Delete by tombstone first, then files, then rows

- Status: Accepted
- Date: 2026-10-28

## Context

- DESIGN v0.1 deleted files first and then rows, with a retry job (DESIGN section 5). Between the request and the end of the delete, the profile and media could still be public.
- Deleting is a privacy control (PRD NFR-8). A half-failed delete must not report success or leave rows that point at missing files (ADR-0008 asked whether a tombstone remains).
- Data model D12 and section 6 define the order.

## Decision

- Principle: hide first (one transaction), delete files second, delete rows last.
- Dog delete (staff only): one transaction sets `dog.status='deleted'`, `deleted_at`, clears `public_slug`, cancels queued jobs of the dog, and enqueues `purge_dog` (`max_attempts=8`). Profile and media return `404` from that moment. The API answers `202 Accepted`.
- `purge_dog` waits while any job of the dog is running, deletes the Storage prefix `dogs/{dog_id}/`, verifies the prefix is empty, then deletes rows in dependency order in one transaction.
- If the purge fails 8 times, the dog row stays `deleted` and the operator sees it in `purge_pending`.
- Clip delete follows the same pattern with `purge_clip` (facts that lose all evidence become `deleted`; confirmed facts that keep other evidence return to `draft`).
- The tombstone is transient: it lives only until the purge finishes.

## Alternatives considered

- Files first, then rows (v0.1): rejected, content stays public during a slow or failing delete.
- Rows first: rejected, a file delete failure leaves orphaned files with no way to find them.
- Soft delete kept forever: rejected, NFR-8 asks for removal.

## Consequences

- Positive: instant hiding; a failed delete is visible and retryable; no false success.
- Negative: asynchronous (`202`); a stuck purge needs operator action; deleted-dog draft-acceptance counts are lost with the facts.

## Related

PRD REV-6, NFR-8; data model D12, 6.1, 6.2; ADR-0008, ADR-0017, ADR-0018.
