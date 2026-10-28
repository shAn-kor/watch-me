# ADR-0010: Nonprofit model, very low cost per listing, contributor pricing only with opt-in

- Status: Accepted
- Date: 2026-10-28

## Context

- SERVICE.md section 8 (decided 2026-10-28): free for shelters, rescues, fosters, adopters; funded by grants and donations (specific programs unverified).
- Shelters lack staff: Korea about 84 rescued animals per center staff member per year (computed, indicative); ASPCA cites staffing shortages (research 1.3, 2.1).
- Muse prices: `muse-spark-1.3` $1.25/1M input, $4.25/1M output; `muse-spark-1.3-contributor` $0.10/$0.20 but Meta may train on content; Voice Transcribe $0.18/hour (DESIGN section 15).
- Best Friends guidance: do not enter sensitive data into free tools (research 1.3).

## Decision

- No fees for end users. Keep cost per listing very low; measure it early (NFR-2: fit the US$150 hackathon credit in R1; long-term target under US$0.50 per listing).
- Prefer open-weight models (Muse Glimmer / Spark Open) on low-cost inference for routine work, reached through `openai_compat` (host availability to verify); paid API only where it adds clear value (SERVICE.md section 8).
- The contributor tier is used only for clips with explicit opt-in (NFR-5).
- Every AI call writes a `cost_ledger` row (ADR-0033).

## Alternatives considered

- Subscription or per-listing fees to shelters: rejected in the decided plan.
- Always use the contributor tier: rejected, clips can show volunteers' faces and need consent.
- Ads or adopter fees: not discussed in the inputs.

## Consequences

- Positive: aligns with shelter budgets.
- Negative: funding is unverified; cost target is unmeasured.

## Resolved issues

- Resolved (project lead, 2026-10-28): R1 reaches open-weight models (Muse Glimmer / Spark Open) through the existing `openai_compat` adapter, pointed at any OpenAI-compatible host of those models. Hosting availability is "(verify)". No separate open-weight adapter is built (ADR-0019).

## Related

PRD NFR-2, NFR-5; ADR-0019, ADR-0033.
