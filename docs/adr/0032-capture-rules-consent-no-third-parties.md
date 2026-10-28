# ADR-0032: Capture rules, member consent, and no third parties in frame

- Status: Accepted (added: decision found in PRD/SERVICE.md)
- Date: 2026-10-28

## Context

- Clips may show volunteers' faces and voices; minors or third parties may appear (PRD section 9 risk).
- SERVICE.md section 12: members agree that their faces and voices may appear; face blur is P2 (SAM 3.1 candidate).
- Best Friends guidance warns against putting adopter or sensitive data in free tools (research 1.3). Legal: US state biometric laws and Korea PIPA need review before real launch (NFR-9).

## Decision

- ORG-4: members accept a consent notice before any upload.
- CAP-7: a capture rules screen on every new session: only the dog and the consenting member in frame.
- REV-9: before publish, staff confirm no people other than consenting members appear in any clip.
- NFR-5: clips are private until published; training use only with opt-in. NFR-8: staff delete a dog or a clip and storage copies are removed.
- AI-5 face blur is R2; move to R1 only if the spike finishes early.
- Adopter questions: no sign-in, rate-limited; personal data stripped before they reach staff (QA-5, R2).

## Alternatives considered

- Rely on face blur alone: deferred to R2.
- Open filming with no rules: rejected by the red-team finding.

## Consequences

- Positive: documented consent chain and a deletion path.
- Negative: the check relies on staff diligence; there is no automatic detection of people in R1.
- Follow-up: legal review before launch; terms page in R1.

## Related

PRD ORG-4, CAP-7, REV-9, NFR-5, NFR-8, NFR-9, AI-5; ADR-0003, ADR-0008, ADR-0010.
