# Design Consistency Report: Watch Me! R1

## 1. Scope and date

Date: 2026-10-28. Covers PRD v1.3, DESIGN.md v0.3, design docs 01 to 07 (all v0.2), and ADR 0001 to 0044.
Precedence when documents disagree: D1-D11 > 01/02 > 04 (AI specifics) > 03 > 05 > 06 > 07 > DESIGN.md.
Documentation only. No code was written.

## 2. Conflicts found and resolutions

| # | Doc | Conflict | Resolution | Source |
|---|-----|----------|------------|--------|
| 1 | 04, 06, 07 | `JobError` shape: 04 had `retryable, fail_code, retry_after_s`; 06 had `RetryableJobError`/`FatalJobError`; 01/02 had `JobError(code, retryable)` | One type `JobError(code, retryable)` plus optional `retry_after_s` (and `usages`). `code` is the stored fail code; there is no `fail_code` field on the exception. Adapters raise it at their boundary via 06 `to_job_error`. `RetryableJobError`/`FatalJobError` removed everywhere | D2, ADR-0042 |
| 2 | 04 | 04 7.4 appended raw ref text to `qa_log.dropped_ids`; 02 defines an integer | Integer count in DB and API; raw text appears in logs only | 02 2.12 |
| 3 | 03 | Diagram D14 called `WordingChecker.check_batch` | Renamed to `check` (matches 04 and 06) | 04 section 2 |
| 4 | 02 | F5 guard 7 required acknowledgement for any non-empty `flags` | Only `warn` flags need `acknowledge_flags=true`; `info` (`check_unavailable`) does not. D15 row aligned | 02 2.8, 04 6.1 |
| 5 | 01 | ffprobe timeout had no error code | 415 `unsupported_file_type`, `details.reason="probe_timeout"` | 06 M7, 07 API-UP-19 |
| 6 | 01, 07 | New session on a deleted dog listed both `invalid_state` and `not_found` | `not_found` only (deleted dogs are hidden). `invalid_state` stays for `published`/`adopted`. 07 API-SES-05 fixed | D10, 01 5.1 |
| 7 | 07 | Stale `DbCostRecorder`; stale "no RetryableJobError" wording | `CostService`; wording rewritten to the single `JobError` shape | 06 |
| 8 | 03 | B2 error list missed `published` for `invalid_state` | Added | 01 5.1 |
| 9 | 03 | T8 source cited 01 5.6 for `media_url` | Changed to 01 section 2 | D7 |
| 10 | 04 | 8.8 claimed 02 J4 "needs the change" | Removed; 02 J4/J5 already state the contract | D2 |
| 11 | 04, 05 | Items in 04 s.11 and 05 s.12/13 still marked open after D1-D10 | Marked Resolved or accepted with the D# | D1-D10 |
| 12 | 06 | AI layer used old types, `TIMESTAMP_MODE`, `AI_CALL_TIMEOUT_S`, cap 5.00, `AiInvalidOutputError` | Rewritten to 04 types, `DRAFT_MODE`, `AI_TIMEOUT_S=75`, cap 3.00, `AiInvalidOutput` | D1, D2, 04 |
| 13 | 06 | Cost recorder, merge/zero-fact/review_ready_at/retry-merge/media_url/SPA rules missing | Added `CostService`, `MergeService` contract, `enqueue_merge`/`mark_review_ready`, `retry_merge`, `MediaUrls`, `api/spa.py` | D3-D8 |
| 14 | 07 | Test catalog predated D1-D11 | 523 cases updated or added per D1-D11 and 04 10.1/10.2 | D1-D11 |
| 15 | 06 M-table | M7, M26, M27, M29, M30 were "Open" | Marked Resolved | rows 1 to 5 |
| 16 | 01, 03, 05, 06, 07 | Upload (01 5.3), add fact (01 5.12) and checklist (01 4.6) gave `invalid_state` for a `deleted` dog, against the hidden-resource rule | `not_found` on every route for a `deleted` dog. 03 B2, 05 copy, 06 `SessionService.create`/`add_manual`/`set_checklist`, 07 API-DEL-04/API-ADD-03 aligned | 01 section 1 (hidden resources), D10 |

Rows 8 to 14 come from the three alignment logs; rows 1 to 7, 15 and 16 are the final pass.

## 3. PRD R1 coverage checklist

Count of mentions of each ID (rg over `design/`). 42 R1 IDs, none missing.

| ID | 01 | 05 | 07 | | ID | 01 | 05 | 07 |
|----|----|----|----|-|----|----|----|----|
| ORG-0 | 4 | 3 | 18 | | PUB-8 | 3 | 2 | 6 |
| ORG-4 | 4 | 4 | 14 | | PUB-9 | 5 | 3 | 13 |
| CAP-1 | 5 | 3 | 9 | | QA-1 | 3 | 4 | 26 |
| CAP-2 | 3 | 3 | 7 | | QA-2 | 2 | 3 | 23 |
| CAP-3 | 2 | 2 | 8 | | QA-4 | 2 | 3 | 9 |
| CAP-4 | 4 | 3 | 22 | | QA-7 | 3 | 1 | 23 |
| CAP-7 | 4 | 2 | 6 | | AI-1 | 1 | 1 | 9 |
| CAP-8 | 12 | 2 | 66 | | AI-2 | 3 | 1 | 43 |
| CAP-9 | 4 | 1 | 10 | | AI-3 | 4 | 3 | 24 |
| REV-1 | 3 | 3 | 7 | | AI-8 | 2 | 1 | 15 |
| REV-2 | 6 | 4 | 37 | | NFR-1 | 2 | 1 | 13 |
| REV-3 | 2 | 2 | 11 | | NFR-2 | 2 | 1 | 12 |
| REV-4 | 3 | 2 | 17 | | NFR-3 | 2 | 1 | 6 |
| REV-5 | 2 | 5 | 18 | | NFR-4 | 2 | 3 | 3 |
| REV-6 | 4 | 3 | 18 | | NFR-5 | 4 | 1 | 37 |
| REV-9 | 6 | 4 | 15 | | NFR-7 | 1 | 1 | 7 |
| REV-10 | 4 | 2 | 9 | | NFR-8 | 5 | 2 | 24 |
| PUB-0 | 4 | 5 | 6 | | NFR-9 | 2 | 3 | 4 |
| PUB-1 | 3 | 2 | 13 | | PUB-2 | 1 | 2 | 13 |
| PUB-3 | 2 | 3 | 8 | | PUB-4 | 2 | 3 | 7 |
| PUB-7 | 3 | 3 | 4 | | | | | |

Gaps: none by ID presence. Thin spots worth a look (a mention is not a proof of full coverage): AI-1 and NFR-7 have one mention in 01; NFR-4 has 3 cases in 07; QA-7 has one mention in 05 (it is an offline eval, so this is expected).

## 4. Open items by owner

**User**
- Meta API key and the $150 credit: arrival not confirmed (04 open Q1, ADR-0029, D11).
- Oracle Cloud signup.
- Dog clips for the day-1 spike (ADR-0029).

**Day-1 spike (verify)**
- Strict mode: are `minLength/maxLength/minItems/maxItems` enforced?
- Output cap parameter names (`max_tokens` or `max_completion_tokens`) and `reasoning_effort` values.
- Cached-token reporting in `usage`.
- Token counts per call (cost model inputs).
- Muse maximum video duration.
- Korean ASR quality (ADR-0024).
- Timestamp accuracy bar (ADR-0029, 04 10.1).
- 05 s.13 item 12: HEIC decoder availability (else drop HEIC from S4 text and `accept`).
- From the 07 log: UT-QA-10 inner spaces in refs ("F 3"); PIPE-TRC-05 which ffmpeg exit codes map to `unsupported_file` vs `transcode_failed`; API-EDT-05 `problem` value for more than 3 evidence rows; API-MET-08 clearing rule for the `ai_auth_error` alert; UT-JOB-05 handling of non-`JobError` exceptions (proposal: non-retryable, 06 M31); reverse proxy body limit of at least 210 MiB (01 5.3).
- Also unspecified: source of `alerts` in `/api/admin/metrics` (06 leaves it to `MetricsService`); config name `AI_PRICES_FILE` is a 06 proposal.

**ADR-level decisions**
- ADR-0001: Best Friends tool scope.
- ADR-0024: Korean ASR quality.
- ADR-0029: spike provider and clips.
- 05 s.13 items 6 (consent and Terms copy owner), 8 (rubber-stamping hold-off), 11, 14, 15 (UX choices).

**R2 (deferred)**
- Volunteer raising concerns in-app (D10), per-range clip cutting (D9), dark theme, face blur, org sign-up, resumable upload, bilingual profile, report queue.

**New in this pass**
- `StructuredCaller` is still the live 06 class name (06 sections 2 and 4.6); 07 uses it correctly. It is not stale.

## 5. Notes

`_lead-decisions.md` stays as the D1-D11 source. The `_align-log-*.md` files are folded into this report and removed.
DESIGN.md cites `design/00-consistency-report.md`; this file is at that path.
