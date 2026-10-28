# ADR-0019: AI provider abstraction with four interfaces and config-chosen adapters

- Status: Accepted (dev provider still undecided)
- Date: 2026-10-28

## Context

- DESIGN section 1: "Dev uses free providers; Muse models in the build for judging."
- The Meta credit has not arrived at the time of writing (DESIGN section 4: "until the Meta credit arrives"). R1 must fit the US$150 hackathon credit (NFR-2).
- Muse API is OpenAI-compatible for Chat Completions (DESIGN section 15) but Voice Transcribe is not (DESIGN section 4).
- Free tiers may train on inputs; real volunteer clips must not go there (DESIGN section 4).

## Decision

- Protocols: `Transcriber`, `FactDrafter`, `WordingChecker`, `FactSelector`; config keys `AI_TRANSCRIBER`, `AI_DRAFTER`, `AI_CHECKER`, `AI_SELECTOR`.
- Adapters: `mock` (deterministic fixtures), `openai_compat` (base_url, model, api_key; covers Muse Spark `https://api.meta.ai/v1`, `muse-spark-1.3`), `local_whisper` (faster-whisper on CPU), `muse_transcribe`, `rules` (banned-word list only).
- Every adapter: structured output only, validated by Pydantic; one retry inside the adapter with the validation error appended, then the job fails at once with `ai_invalid_output` (no job-level retry; job retries cover transient errors only, ADR-0017). Every call writes a `cost_ledger` row.
- Open-weight models (Muse Glimmer / Spark Open): reached through `openai_compat` pointed at any OpenAI-compatible host of those models (hosting availability to verify). No separate adapter (ADR-0010).
- Dev provider: undecided; pick one free `openai_compat` endpoint with image input, or run `mock`. Never send real volunteer clips to a tier that trains on inputs.

## Alternatives considered

- Hard-code the Muse SDK: rejected, blocks dev work before the credit arrives and locks in one vendor.
- Single provider for all roles: rejected, ASR is not OpenAI-compatible.

## Consequences

- Positive: dev without credits; provider swap by config; testable with `mock`.
- Negative: adapter surface to maintain; prompts may behave differently across models (inference).
- Follow-up: choose the dev provider (DESIGN section 13).

## Resolved issues

- Resolved (project lead, 2026-10-28): the open-weight route from ADR-0010 needs no new adapter; `openai_compat` with a different `base_url` and `model` is enough.

## Related

PRD AI-1..AI-3, AI-8, NFR-2; ADR-0010, ADR-0020, ADR-0022, ADR-0023, ADR-0024, ADR-0033.
