# ADR-0012: Cut R1 to one seeded end-to-end path; no sign-up or organization verification

- Status: Accepted
- Date: 2026-10-28

## Context

- Hackathon deadline: 2026-11-05 11:00 KST (PRD header). Red-team review cut R1 to one seeded path.
- SERVICE.md section 12 describes full onboarding with proof (Korea: registered center; US: 501(c)(3) or public listing); data sources for automatic checks are unverified.
- Fake organizations are a risk (PRD section 9). Anti-project risk: "simple RAG"; lead with video-to-timestamped-evidence.

## Decision

- R1 runs with one seeded organization, one staff and one volunteer account (ORG-0), configured by seed (`tools/seed.py`); the org shows without a verified badge. Members accept a consent notice before upload (ORG-4).
- R1 path: day-1 timestamp spike; seed; capture and processing; review and publish; public profile; Q&A (PRD section 7).
- Cut first if time runs short, in order: REV-10, CAP-2, QA-1 per-cookie limit (keep the cost cap). Safety controls (PUB-0, PUB-8, PUB-9, REV-9, QA-2) are never cut.
- R2: ORG-1 sign-up with proof, ORG-2 operator approval and badge, ORG-3 invite links (expire after 7 days).

## Alternatives considered

- Sign-up plus manual verification in R1: rejected, time and unverified data sources.
- Open sign-up with no verification: rejected, fake organizations risk.

## Consequences

- Positive: reachable by the deadline; verified badge cannot be misused.
- Negative: not a usable multi-shelter product; trust signals (verified badge) absent.

## Resolved issues

- Resolved (project lead, 2026-10-28): PRD v1.2 wins over SERVICE.md. The proof method for R2 is PRD ORG-1 (US EIN checked against the IRS tax-exempt list; Korea registration number), not the SERVICE.md 501(c)(3) or Petfinder-listing wording. R1 uses seeded password login, not invite links; invite links are R2 (ORG-3).
- Resolved (PRD v1.2): PUB-9 and the other safety controls are never cut. The cut order is now REV-10, CAP-2, QA-1 per-cookie limit (keep the cost cap).

## Related

PRD ORG-0..ORG-4, section 7; ADR-0003, ADR-0025, ADR-0029.
