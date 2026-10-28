# ADR-0006: No adoption applications in the app; contact goes through the shelter's own channel

- Status: Accepted
- Date: 2026-10-28

## Context

- Process barriers lower adoption rates: 3 or more barriers were about 7 points lower than none; "a listing tool does not fix this" (SAC survey, research 1.2).
- 38% of people who inquired on Adopt-a-Pet never heard back (secondary data, research 1.2).
- Korea: 19.5% of non-adopters do not know the adoption method or procedure (research 2.2).
- SERVICE.md section 11 (decided): the app does not run adoption applications.

## Decision

- The profile shows a contact block using the shelter's own channel (org `contact_url`, `contact_email`, `contact_phone`) (PUB-7). No in-app application form.
- Non-goals: no adoption applications, payments, or matching (PRD section 2).

## Alternatives considered

- In-app application workflow: rejected, adds scope and regulatory surface; the tool cannot fix process barriers.
- Adopter accounts: no sign-in for adopters in R1 (PRD section 3).

## Consequences

- Positive: small scope; shelters keep their own process.
- Negative: no tracking of whether inquiries get answered (the 38% problem is not addressed).
- Follow-up: R2 request inbox ("film this next") may collect adopter questions (QA-3, QA-5, QA-6).

## Related

PRD PUB-7, section 2 non-goals; ADR-0007.
