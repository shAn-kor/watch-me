# ADR-0022: Q&A: the model returns fact IDs only; the server renders all text

- Status: Accepted
- Date: 2026-10-28

## Context

- Red-team review: Q&A could drift into claims or follow injected instructions (PRD section 9).
- SERVICE.md described answers from recorded evidence; PRD v1.1 rebuilt Q&A as fact-ID selection with an adversarial test set.
- Hackathon anti-project risk: "simple RAG"; Q&A is a constrained lookup (PRD section 9).

## Decision

- Flow (DESIGN section 7): check limits and the daily cost cap; a health keyword or classifier hit returns the fixed template ("Ask the shelter's vet."); send the question plus this dog's confirmed facts `{id, situation, behavior}` to `FactSelector` using per-request aliases F1..Fn mapped back to ids by the server (ADR-0037); keep only IDs of this dog's confirmed facts; render.
- Empty list renders "Not observed yet." (with the matching situation if known); otherwise the selected facts with clip links under a fixed lead line ("Here is what has been filmed:"). Log to `qa_log`.
- The model never writes text that reaches the adopter (QA-2).
- Limits (QA-1): 10 per hour per IP hash and per cookie; global daily cost cap.
- QA-7: at least 50 adversarial questions. Bar: 0 answers cite a fact outside the dog's confirmed set. Target: at least 95% of no-evidence questions return "Not observed yet"; report the measured rate. Runner `tools/qa_eval.py`, data `eval/qa_adversarial.jsonl`.

## Alternatives considered

- Free-text RAG answers: rejected, could invent claims or follow injected text.
- Retrieval without a model (keyword match): not discussed in the inputs.

## Consequences

- Positive: no diagnosis or trait wording is possible; injected text cannot reach the page.
- Negative: answers are rigid; paraphrase matching depends on the model's selection quality (rate unmeasured).

## Resolved issues

- Resolved (PRD v1.2): QA-4 R1 renders only the fixed vet template; adding transcribed records waits for AI-4 (R2).
- Resolved: SERVICE.md P0 evidence-only Q&A with a send-to-shelter loop is the earlier plan; PRD v1.2 wins and that loop is R2 (QA-3).

## Related

PRD QA-1..QA-7, AI-8, G3; ADR-0023, ADR-0033.
