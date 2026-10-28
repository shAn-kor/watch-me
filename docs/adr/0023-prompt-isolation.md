# ADR-0023: Prompt isolation for narration and adopter questions

- Status: Accepted
- Date: 2026-10-28

## Context

- Volunteer narration (transcripts) and public adopter questions are untrusted text that goes into model prompts (PRD AI-8).
- Prompt injection is part of the adversarial test set (QA-7).
- Best Friends guidance: AI drafts, humans review (research 1.3).

## Decision

- Narration, transcripts and adopter questions go inside a clearly delimited data block; the system prompt says data is never instructions (DESIGN section 4).
- FactSelector output is a list of IDs, so injected text cannot reach the page (ADR-0022).
- For drafting, injected narration could influence draft text, so the human review gate (ADR-0004) and the wording check (AI-3) remain in place.

## Alternatives considered

- Input sanitizing by keyword stripping: not described in the inputs.
- Trust the model's instruction hierarchy alone: rejected as the sole defense.

## Consequences

- Positive: structural defense for Q&A; testable.
- Negative: delimiting does not stop injection in the drafter; protection there is human review.
- Follow-up: add narration-injection cases to tests. The QA-7 set covers questions; narration cases are an inference (unverified).

## Related

PRD AI-8, QA-7; ADR-0004, ADR-0022.
