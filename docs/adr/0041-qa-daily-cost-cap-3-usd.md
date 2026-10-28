# ADR-0041: Q&A daily cost cap defaults to 3.00 USD

- Status: Accepted
- Date: 2026-10-28

## Context

- ADR-0033 introduced `QA_DAILY_USD_CAP` and left the value open ("pick the cap value").
- The hackathon budget is a $150 credit (project lead, 2026-10-28). Draft and check calls on uploads use most of it; Q&A must not drain it.

## Decision

- `QA_DAILY_USD_CAP` defaults to 3.00 USD per UTC day, summed from `cost_ledger` rows of Q&A calls.
- Past the cap, Q&A answers with the stop message; health and no-facts answers still work (no model call).
- The value is a setting and can change without code.

## Alternatives considered

- A lower cap (for example 1.00): rejected, a single demo day could hit it.
- No default: rejected, an unset cap means no protection.

## Consequences

- Positive: bounded worst case, about 3.00 USD per day over a demo period.
- Negative: an attacker or a busy day can switch Q&A off for the rest of the UTC day (ADR-0033).

## Related

PRD QA-1, NFR-2; ADR-0010, ADR-0033; 04-ai-design cost model.
