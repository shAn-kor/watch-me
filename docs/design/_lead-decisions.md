# Lead decisions D1-D11 (Watch Me! design, 2026-10-28)

D1. `QA_DAILY_USD_CAP` default = 3.00 USD (fits the $150 hackathon credit).
D2. Error/retry contract: AI adapters raise `JobError(code, retryable: bool)`. Schema-invalid output: one in-adapter retry, then `ai_invalid_output`, not retryable. Non-transient provider errors (HTTP 400/401/402/403/404, including image errors): fail at once, `ai_failed`, not retryable, no automatic retry. Transient (network, timeout, 429, 5xx): job-level retry up to max_attempts. Users can still retry a failed clip manually.
D3. Cross-clip merge (from 04): duplicate facts merge their evidence ranges instead of hard deletion (02 F2 and related tests).
D4. If post-processing drops every fact of a clip, the clip is `ready` with zero facts (not a failure). Review shows "No facts were drafted from this clip. Add one by hand if you saw something."
D5. `review_ready_at`: cleared when a merge is (re)enqueued; set when the latest merge completes.
D6. `POST /api/sessions/{id}/retry-merge` (session owner or staff) for a merge-failed/failed session; in 01, 02 transitions, 03, 05, 06, 07.
D7. Creator fact responses include `media_url` (same shape as public) so the player never builds URLs.
D8. Hidden profile: the public API returns 404 `not_found`; the SPA HTML is served with 200 and renders the not-available page. PRD REV-5 AC: "the public API returns HTTP 404; the page says 'not available'".
D9. Whole clip files of cited clips are publicly reachable; the public player plays only the cited range. Accepted for R1, disclosed in the publish dialog. Per-range clip cutting is R2.
D10. Volunteer raising concerns to staff in-app: R2. Light theme only in R1. Review in two scopes (per session, per dog): accepted. New session blocked for published/adopted dogs: accepted.
D11. Remaining verify items stay "(verify)" for the day-1 spike: strict-mode min/max enforcement, output-cap parameter names, cached-token reporting in `usage`, token counts, Muse max video duration, Korean ASR quality. Meta key/credit and dev provider are user-side open items.

Precedence on conflicts: D1-D11 > 01/02 > 04 (AI specifics) > 03 > 05 > 06 > 07 > DESIGN.md.
