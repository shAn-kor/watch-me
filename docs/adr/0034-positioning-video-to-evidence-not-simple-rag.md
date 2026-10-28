# ADR-0034: Lead with video-to-timestamped-evidence; Q&A is a constrained lookup, not free chat

- Status: Accepted (added: decision found in PRD)
- Date: 2026-10-28

## Context

- Hackathon anti-project risk: "simple RAG" (PRD section 9).
- IDEAS.md criteria include uses Meta model strengths and not an anti-project.
- PRD section 1: the core is video-to-timestamped-evidence; Q&A is a constrained lookup over confirmed facts.
- Existing alternatives show no evidence behind claims (SERVICE.md section 4 table).

## Decision

- The pitch and the demo lead with: video in, facts with clip ranges out, a human confirms, adopters tap a fact and watch the moment.
- Q&A is presented as selecting from confirmed facts (ADR-0022), not as a general chatbot.
- The Muse models handle the video-heavy work (frames, narration ASR), as in DESIGN section 1.

## Alternatives considered

- Lead with a chatbot over shelter data: rejected, the anti-project risk.
- Lead with photo cleanup: rejected, no effect shown (ADR-0001).

## Consequences

- Positive: a differentiated story that matches the evidence.
- Negative: the headline feature depends on timestamp accuracy (ADR-0029).

## Related

PRD section 1, section 9; ADR-0001, ADR-0022, ADR-0029.
