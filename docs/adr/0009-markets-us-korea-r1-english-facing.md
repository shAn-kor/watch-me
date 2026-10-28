# ADR-0009: Target US and Korea, but R1 is English-facing; Korean UI and bilingual profiles in R2

- Status: Accepted
- Date: 2026-10-28

## Context

- SERVICE.md section 2 (decided 2026-10-28): US and Korea from day one, bilingual (English/Korean) profiles; supports Korea-to-US overseas adoption (flow size unverified).
- Evidence exists in both markets (research sections 1 and 2). Korea's top adoption condition is verified health and vaccination (35.3%), which needs AI-4 (R2).
- Red-team review: "Korea scope stated honestly" (PRD header). The hackathon build is due 2026-11-05 11:00 KST.
- SERVICE.md section 6 says PRD release scope overrides its P0-P2 list.

## Decision

- R1: English UI; narration may be Korean or English (NFR-4, AI-1 acceptance: both work).
- R2: Korean UI, bilingual profiles (REV-8), vaccination record transcription (AI-4).
- Do not claim Korea features R1 does not have (PRD section 7).

## Alternatives considered

- Bilingual from R1: rejected for hackathon time (reasoning implied by PRD scope cut; not stated in the inputs).
- US only: rejected, Korea is a stated market and evidence base.

## Consequences

- Positive: honest claims; Korean narration still supported at input.
- Negative: R1 does not serve Korean adopters; the Korean evidence (35.3%) is addressed only in R2.

## Resolved issues

- Resolved (project lead, 2026-10-28): PRD v1.2 wins over SERVICE.md. SERVICE.md sections 2 and 6 ("bilingual from day one") are the earlier plan. Bilingual profiles are R2. SERVICE.md is not edited.

## Related

PRD NFR-4, REV-8, AI-1, AI-4; ADR-0011, ADR-0012, ADR-0024.
