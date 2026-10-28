# ADR-0033: Cost ledger for every AI call and a daily cost cap on Q&A

- Status: Accepted (added: decision found in PRD/DESIGN)
- Date: 2026-10-28

## Context

- Q&A is public, unauthenticated and calls a paid model (PRD QA-1). Abuse could drain the US$150 hackathon credit.
- Cost per listing is a core goal (ADR-0010; NFR-2 measure in the spike).
- Muse prices: `muse-spark-1.3` $1.25 / 1M input, $4.25 output; Voice Transcribe $0.18/hour (DESIGN section 15).

## Decision

- Every AI call writes a `cost_ledger` row: provider, model, tokens in/out, estimated USD, purpose (DESIGN section 4).
- Q&A refuses when the day's Q&A spend in `cost_ledger` passes `QA_DAILY_USD_CAP`; this shows the user a stop message rather than an error (stop-message wording not specified in the inputs).
- Rate limits: 10 questions per hour per IP hash and per cookie (QA-1). The per-cookie limit is cut first if time runs short; the cost cap stays (PRD section 7).

## Alternatives considered

- No cap, rely on rate limits: rejected, a distributed attack can pass per-IP limits (inference).
- Require sign-in for Q&A: rejected, adopters have no account in R1.

## Consequences

- Positive: bounded spend; data for NFR-2 and for the cost-per-listing goal.
- Negative: an attacker can exhaust the cap and turn Q&A off for everyone that day (inference).
- Follow-up resolved: the default cap is 3.00 USD (ADR-0041).

## Related

PRD QA-1, NFR-2; DESIGN sections 4, 7; ADR-0010, ADR-0019, ADR-0022.
