# ADR-0037: Q&A sends per-request aliases F1..Fn instead of fact IDs

- Status: Accepted
- Date: 2026-10-28

## Context

- DESIGN v0.1 sent `{id, situation, behavior}` with 32-character hex ids and expected the model to return ids (ADR-0022).
- Models copy long hex ids badly; a single wrong character makes a valid selection look like an out-of-set citation (API spec A10).
- The server filter on the allowed set must stay: QA-7 requires zero out-of-set citations.

## Decision

- For each question, the server numbers the dog's confirmed facts `F1..Fn` and sends `{ref, situation, behavior}`.
- The model returns a JSON list of refs. The server maps refs back to fact ids, drops anything not in the set (counted in `qa_log.dropped_ids`), removes duplicates, and keeps at most 5 (`QA_MAX_FACTS`).
- Aliases exist for one request only; no stable ref is stored or exposed.
- Everything else in ADR-0022 is unchanged: fixed lead line, fixed vet template, "Not observed yet.", and no model text reaches the adopter.

## Alternatives considered

- Full hex ids: rejected, copy errors.
- Short stable ids stored on the fact: rejected, adds a column and makes injected guesses possible across requests.
- Fact text as the key: rejected, long and duplicated across facts.

## Consequences

- Positive: fewer false drops; shorter prompts and lower token cost; the allowed-set check still enforces safety.
- Negative: prompts and logs show refs, not ids, so debugging needs the per-request map (logged in `qa_log`).

## Related

PRD QA-2, QA-7; API spec 7, A10; ADR-0022, ADR-0023.
