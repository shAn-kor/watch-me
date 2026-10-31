# Watch Me! R1: API Specification (v0.2, 2026-10-28)

Input: `docs/PRD.md` v1.3 (R1 only) and `docs/DESIGN.md` v0.3 section 6 (plus 7, 9). v0.2 applies lead decisions D1-D11 and adopts additions from 03-07 (see section 10, A24 onward). This file and `02-data-model.md` are the authority for names, fields, statuses and error codes; `00-consistency-report.md` lists what was reconciled.
Companion: `02-data-model.md` (tables, state machines, derived values). Table
and column names below refer to it. "(verify)" marks an unchecked assumption.
Where this file departs from DESIGN.md v0.1, see the last section.

## 1. Conventions

| Topic            | Rule                                                                                                                                                                                                                                                                                                                                                                                  |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Base path        | JSON API under `/api`. Media under `/media`. Health at `/healthz`. The SPA build is served by the same origin (no CORS).                                                                                                                                                                                                                                                              |
| Content type     | Requests and responses are `application/json; charset=utf-8`, except multipart upload endpoints and media. A JSON `POST` without `Content-Type: application/json` gets `415 unsupported_media_type`.                                                                                                                                                                                  |
| JSON casing      | `snake_case` for every key and enum value.                                                                                                                                                                                                                                                                                                                                            |
| Ids              | Strings. Entity ids are 32-char lowercase hex. Public slugs are 12 chars of `[a-z2-9]`.                                                                                                                                                                                                                                                                                               |
| Timestamps       | RFC 3339 UTC with `Z`, second precision: `2026-10-28T13:22:05Z`.                                                                                                                                                                                                                                                                                                                      |
| Dates            | `YYYY-MM-DD` (`observed_on`).                                                                                                                                                                                                                                                                                                                                                         |
| Seconds in clips | JSON numbers, 0.1 s precision (`start_s`, `end_s`, `duration_s`). Whole numbers for display totals (`seconds`, `filmed_s`).                                                                                                                                                                                                                                                           |
| Pagination       | None in R1. `GET /api/dogs` returns up to 200 dogs, newest first. No other list can exceed 50 items.                                                                                                                                                                                                                                                                                  |
| Auth cookie      | `wm_session`: signed (itsdangerous, `SECRET_KEY`), `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, max age 7 days. Payload: member id, issue time, `session_epoch`, random `sid`. `Secure` is off only when `COOKIE_SECURE=false` in local dev.                                                                                                                                       |
| CSRF             | Every state-changing request that uses `wm_session` (`POST`, `PUT`, `PATCH`, `DELETE`) must send header `X-CSRF-Token: <token>`. Token = `HMAC-SHA256(SECRET_KEY, "csrf:" + sid)`, hex. Returned in the `csrf_token` field of `POST /api/auth/login` and `GET /api/me`. The SPA keeps it in memory and refetches `/api/me` on reload. Missing or wrong token gives `403 csrf_failed`. |
| Visitor cookie   | `wm_visitor`: random 16 bytes hex, `HttpOnly`, `Secure`, `SameSite=Lax`, max age 1 year. Set by the first `ask` call. Only used for the Q&A limit. Not an account.                                                                                                                                                                                                                    |
| Public endpoints | No auth, no CSRF. `POST` on public endpoints still requires `Content-Type: application/json` (a cross-site HTML form cannot send it).                                                                                                                                                                                                                                                 |
| Org scope        | Every creator query filters by the member's `org_id`. Anything in another org returns `404 not_found`.                                                                                                                                                                                                                                                                                |
| Hidden resources | Unpublished, adopted, and deleted dogs return `404 not_found` on public API and media routes, with the same body as an unknown slug. The SPA HTML for `/d/{slug}` is a static shell served with `200` for every slug; the frontend calls the public API and renders the "not available" page on `404` (ADR-0040). |
| Caching          | API responses: `Cache-Control: no-store`. Media: section 6.                                                                                                                                                                                                                                                                                                                           |
| Robots           | Public profile responses and the SPA route `/d/{slug}` send `X-Robots-Tag: noindex` (the product has no browse or search; links are shared by the shelter).                                                                                                                                                                                                                           |

### 1.1 Error envelope

```json
{
  "error": {
    "code": "playback_required",
    "message": "Watch the whole clip range before you confirm this fact.",
    "details": { "missing_evidence_ids": ["a1b2c3d4e5f60718293a4b5c6d7e8f90"] }
  }
}
```

`message` is a short English sentence safe to show to the user. `details` is an
object (empty `{}` when unused). Clients branch on `code`, never on `message`.
Validation errors (`422`) carry `details.fields`: a list of
`{ "path": "body.behavior", "problem": "too_long", "limit": 280 }`.

### 1.2 Error code catalog

| HTTP | `code`                         | Meaning                                                                                                                                                                                         | Where                                                  |
| ---- | ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| 400  | `malformed_request`            | Body is not valid JSON or multipart                                                                                                                                                             | any                                                    |
| 400  | `upload_incomplete`            | Upload stream ended before `Content-Length` or the connection broke. Retryable. (CAP-8 "upload failed", server-detected; a network drop on the client is shown by the client as the same state) | clip upload                                            |
| 401  | `unauthenticated`              | No valid `wm_session`                                                                                                                                                                           | creator routes                                         |
| 401  | `invalid_credentials`          | Wrong email or password (one message for both)                                                                                                                                                  | login                                                  |
| 403  | `csrf_failed`                  | Missing or wrong `X-CSRF-Token`                                                                                                                                                                 | state-changing creator routes                          |
| 403  | `forbidden_role`               | Role is not allowed for this action (volunteer on a staff action)                                                                                                                               | many                                                   |
| 403  | `consent_required`             | Member has not accepted the face and voice notice (ORG-4)                                                                                                                                       | create session, upload clip, submit, confirm, add fact |
| 403  | `not_own_session`              | Volunteer acts on a fact or clip from another member's session (REV-4)                                                                                                                          | confirm, edit, delete fact, clip                       |
| 403  | `staff_only_situation`         | Only staff may confirm a `children_cats` fact (PUB-9)                                                                                                                                           | confirm                                                |
| 404  | `not_found`                    | Unknown id, other org, or hidden (unpublished, adopted, deleted)                                                                                                                                | many                                                   |
| 409  | `invalid_state`                | State machine forbids the action (for example confirm on a `confirmed` fact; upload to a non-`open` session or a published dog)                                                                 | many                                                   |
| 409  | `clip_limit_reached`           | Session already has 3 live clips (CAP-4)                                                                                                                                                        | clip upload                                            |
| 409  | `clip_not_ready`               | Clip used in evidence is not `ready`                                                                                                                                                            | add or edit fact                                       |
| 409  | `playback_required`            | A fact range has no completed playback by this member (REV-2). `details.missing_evidence_ids`                                                                                                   | confirm                                                |
| 409  | `flags_unacknowledged`         | Fact has wording flags and `acknowledge_flags` was not true                                                                                                                                     | confirm                                                |
| 409  | `publish_checklist_incomplete` | Publish or confirm-on-published blocked. `details.missing`: any of `people_check`, `known_concerns`, `confirmed_fact` (REV-9)                                                                   | publish, confirm                                       |
| 413  | `file_too_large`               | File over 200 MiB (209,715,200 bytes). CAP-8 "too large". `details.max_bytes`                                                                                                                   | clip upload                                            |
| 415  | `unsupported_file_type`        | Container is not MP4/MOV, ffprobe cannot read the file or finds no video stream, or ffprobe times out (10 s). The file extension is not checked. `details.reason` is `unsupported_container`, `unreadable`, `no_video` or `probe_timeout`; the api logs the reason and the client suffix (WARNING, logger `app.upload`). CAP-8 "unsupported file". `details.allowed`                                                                            | clip upload, photo upload                              |
| 415  | `unsupported_media_type`       | JSON endpoint called with another content type                                                                                                                                                  | any JSON `POST`                                        |
| 422  | `validation_error`             | Field validation failed. `details.fields`                                                                                                                                                       | any                                                    |
| 422  | `clip_too_long`                | Duration over 120 s (a 0.5 s tolerance is allowed). `details.max_s`, `details.duration_s`                                                                                                       | clip upload                                            |
| 422  | `evidence_out_of_range`        | Evidence range is outside the clip, shorter than 1 s, longer than 60 s, or the clip is from another dog                                                                                         | add or edit fact                                       |
| 422  | `question_too_short`           | Question under 3 characters after trim                                                                                                                                                          | ask                                                    |
| 429  | `rate_limited`                 | Limit hit. Header `Retry-After` (seconds). `details.scope`: `ip`, `cookie`, `member`, `login`                                                                                                   | login, upload, ask, public reads                       |
| 500  | `internal_error`               | Unexpected. A request id is in `details.request_id` and the `X-Request-Id` header                                                                                                               | any                                                    |
| 503  | `qa_cost_cap_reached`          | Daily Q&A spend reached `QA_DAILY_USD_CAP` (default 3.00 USD per UTC day, ADR-0033/0041; QA-1). `Retry-After` until 00:00 UTC. Only for questions that need a model call. The health and no-facts paths still answer | ask |
| 503  | `qa_unavailable`            | Selector provider failed (no job retry for Q&A; any provider error), or returned schema-invalid output after the adapter's one retry. No guess is rendered | ask |
| 503  | `storage_unavailable`          | Disk full or storage write failed                                                                                                                                                               | uploads                                                |

Pipeline failures (`unsupported_file`, `too_long`, `transcode_failed`,
`ai_failed`, `ai_invalid_output`) are not HTTP errors. They appear as
`clip.fail_code` (data model section 3.3) together with `clip.error` (cause
text and `retryable`). Two different "retry" notions exist; do not mix them:

- Automatic retry (job level, `JobError.retryable`): AI adapters and handlers raise `JobError(code, retryable: bool)` (ADR-0042). Only transient errors (network, timeout, HTTP 429, HTTP 5xx; for ffmpeg: timeout, kill, disk full) are `retryable=true` and are retried up to `max_attempts`. Schema-invalid AI output is retried once inside the adapter, then fails at once as `ai_invalid_output` (not retryable). Non-transient provider errors (HTTP 400/401/402/403/404, including image errors) fail at once as `ai_failed` (not retryable, no automatic retry).
- Manual retry (`clip.error.retryable`, `POST /api/clips/{id}/retry`): true for `transcode_failed`, `ai_failed`, `ai_invalid_output`; false for `unsupported_file`, `too_long`. A user can always retry such a clip by hand, even after the automatic path gave up. A session in `failed` with `fail_code="merge_failed"` is retried with `POST /api/sessions/{id}/retry-merge` (5.4a).
- A clip whose draft step produced zero usable facts (for example all evidence was invalid after post-processing) is `ready`, not failed (D4; 04 section 5).

Validation problem values in `details.fields[].problem`: `required`, `too_short`, `too_long`, `invalid_value`, `duplicate`, `version_mismatch`, `evidence_required`, `range_not_completed`.

### 1.3 Rate limits (summary)

| Scope                  | Limit                                                          | Window         | Store                          |
| ---------------------- | -------------------------------------------------------------- | -------------- | ------------------------------ |
| `POST /api/auth/login` | 10 attempts per IP and 5 per email                             | 15 min         | memory (single api process)    |
| Authenticated writes   | 120 per member                                                 | 1 min          | memory                         |
| Clip uploads           | 20 per member                                                  | 1 hour         | memory                         |
| `POST .../ask`         | 10 per IP hash and 10 per `wm_visitor` cookie (both must pass) | 1 hour sliding | `qa_log` (rows with `outcome=error` do not count; rejected calls `404`/`422`/`429` write no row; the IP hash restarts at 00:00 UTC because `ip_hash` includes the UTC date) |
| Public `GET` profile   | 120 per IP                                                     | 1 min          | memory                         |
| Media `GET`            | 600 per IP                                                     | 1 min          | memory (verify with the proxy) |

IP comes from the trusted proxy header (`X-Forwarded-For`, last hop) when
`TRUSTED_PROXY=true`, else the socket address (verify against the real deployment).
Memory counters reset on restart; accepted for R1.

## 2. Common objects

`Member`

```json
{
  "id": "9f1c...",
  "email": "vol@example.org",
  "display_name": "Minji",
  "role": "volunteer",
  "consented_at": null,
  "consent_version": null
}
```

`Org`

```json
{
  "id": "3b7d...",
  "name": "Maple Street Rescue",
  "country": "US",
  "location": "Portland, OR",
  "contact": {
    "url": "https://example.org/adopt",
    "email": "adopt@example.org",
    "phone": null
  }
}
```

`Coverage` (data model section 4.1)

```json
{
  "situations_total": 8,
  "situations_covered": 3,
  "by_situation": [
    {
      "situation": "new_person",
      "label": "Meeting a new person",
      "covered": true,
      "clip_count": 2,
      "filmed_s": 74,
      "confirmed_s": 16
    },
    {
      "situation": "children_cats",
      "label": "Children or cats",
      "covered": false,
      "clip_count": 0,
      "filmed_s": 0,
      "confirmed_s": 0
    }
  ],
  "not_observed": [
    { "situation": "children_cats", "label": "Children or cats" }
  ]
}
```

`by_situation` always lists all 8 entries in PRD order. `not_observed` lists the
uncovered ones in the same order.

`Dog` (creator view)

```json
{
  "id": "d0g1...",
  "name": "Biscuit",
  "sex": "male",
  "age_estimate": "about 3 years",
  "size": "medium",
  "location": null,
  "photo_url": "/media/dogs/d0g1.../photo.jpg",
  "status": "draft",
  "public_slug": null,
  "public_path": null,
  "created_by": "9f1c...",
  "created_at": "2026-10-28T09:00:00Z",
  "published_at": null,
  "adopted_at": null
}
```

`public_path` is `/d/{slug}` once a slug exists (also while unpublished, but it
returns "not available" then). `photo_url` is `null` without a photo.

`Checklist`

```json
{
  "people_check": true,
  "people_check_at": "2026-10-28T10:00:00Z",
  "known_concerns": "Pulls hard toward other dogs on leash.",
  "known_concerns_none": false,
  "confirmed_fact_count": 4,
  "ready_to_publish": true,
  "missing": []
}
```

`missing` uses the same values as `publish_checklist_incomplete.details.missing`.

`Clip` (creator view)

```json
{
  "id": "c11p...",
  "session_id": "s355...",
  "ordinal": 1,
  "original_filename": "IMG_0412.MOV",
  "original_size_bytes": 83886080,
  "duration_s": 47.3,
  "has_audio": true,
  "status": "processing",
  "step": "transcribe",
  "fail_code": null,
  "error": null,
  "media_url": null,
  "captions_url": null,
  "created_at": "2026-10-28T09:05:00Z",
  "ready_at": null
}
```

`error` is `null` unless `status="failed"`, then
`{ "cause": "We could not convert this clip.", "retryable": true }`. `media_url` and
`captions_url` are set only when `status="ready"`.

`Fact` (creator view)

```json
{
  "id": "f4c7...",
  "dog_id": "d0g1...",
  "session_id": "s355...",
  "situation": "leash_walk",
  "behavior": "Walked beside the handler on a loose leash for the whole hallway.",
  "source": "clip",
  "origin": "ai_unchanged",
  "status": "draft",
  "flags": [
    {
      "code": "trait_claim",
      "severity": "warn",
      "source": "model",
      "detail": "Possible trait wording: 'well-behaved'"
    }
  ],
  "observed_on": "2026-10-28",
  "evidence": [
    {
      "id": "e7a1...",
      "clip_id": "c11p...",
      "start_s": 12.0,
      "end_s": 21.0,
      "played_by_me": false,
      "media_url": "/media/c11p....mp4",
      "captions_url": "/media/c11p....vtt"
    }
  ],
  "clip_length": { "clip_count": 1, "seconds": 9, "label": "1 clip, 9 s" },
  "confirmed": null,
  "created_by": null,
  "can_confirm": false,
  "blocked_reason": "playback_required"
}
```

Each creator evidence item carries `media_url` and `captions_url` in the same shape as the public API (`captions_url` is `null` when the clip has no transcript rows), so the player never builds URLs from `clip_id` (D7). Both are `null` only if the clip is not `ready`; a fact cannot cite such a clip (`clip_not_ready`).

`confirmed` is `null` or `{ "by_member_id", "by_name", "role", "at" }`.
`can_confirm` and `blocked_reason` are computed for the requesting member
(`null` when allowed; otherwise the first failing confirm guard code from data
model 3.4) so the UI can disable the button with the right hint. The server still
re-checks on confirm. `merged=0` facts are never returned. `deleted` facts are
never returned (a lookup by id of such a fact gives `404 not_found`, so a client cannot learn that a hidden fact exists). Flag values: `banned_word` (severity `warn`, source `rules`), `trait_claim` (`warn`, `model`), `check_unavailable` (`info`, `system`). Clients treat an unknown severity as `warn`; only `warn` flags require `acknowledge_flags` on confirm (`info` does not).

`Session` (creator view)

```json
{
  "id": "s355...",
  "dog_id": "d0g1...",
  "member_id": "9f1c...",
  "owner_name": "Minji",
  "situations": ["leash_walk", "new_person"],
  "observed_on": "2026-10-28",
  "status": "processing",
  "fail_code": null,
  "created_at": "2026-10-28T09:01:00Z",
  "submitted_at": "2026-10-28T09:08:00Z",
  "review_ready_at": null
}
```

`fail_code` is `no_usable_clip` or `merge_failed` while `status="failed"`. `review_ready_at` is cleared when a merge is (re)enqueued and set when the latest merge (including its `check` step) completes (D5).

Situation codes and labels (fixed):

| Code            | Label                |
| --------------- | -------------------- |
| `new_person`    | Meeting a new person |
| `handling`      | Handling             |
| `leash_walk`    | Leash walk           |
| `other_dog`     | Meeting another dog  |
| `food_toys`     | Food and toys        |
| `alone_time`    | Alone time           |
| `indoors_rest`  | Indoors and rest     |
| `children_cats` | Children or cats     |

Fact text rules (validated on write): `behavior` is 3 to 280 characters after
trim and NFC normalization, one line.

## 3. Auth and member

Error rows list endpoint-specific codes only. Every creator endpoint can also
return `unauthenticated`, `csrf_failed` (non-GET), `rate_limited`, `internal_error`.

### 3.1 `POST /api/auth/login`

Auth: none. CSRF: no (no session yet). PRD: ORG-0. Limit: 10 per IP, 5 per email, 15 min.

Request:

```json
{ "email": "vol@example.org", "password": "correct horse battery" }
```

Response `200`: sets `wm_session`; body:

```json
{
  "member": {
    "id": "9f1c...",
    "email": "vol@example.org",
    "display_name": "Minji",
    "role": "volunteer",
    "consented_at": null,
    "consent_version": null
  },
  "org": {
    "id": "3b7d...",
    "name": "Maple Street Rescue",
    "country": "US",
    "location": "Portland, OR",
    "contact": { "url": null, "email": "adopt@example.org", "phone": null }
  },
  "csrf_token": "6f2a..."
}
```

Errors: `invalid_credentials` 401, `validation_error` 422, `rate_limited` 429.

### 3.2 `POST /api/auth/logout`

Auth: member. CSRF: yes. PRD: ORG-0. Body: none.
Response `204`. Clears the cookie and increments `member.session_epoch`.

### 3.3 `GET /api/me`

Auth: member. CSRF: not needed. PRD: ORG-0, ORG-4. (Added: the SPA needs it on every reload.)

Response `200`: same body as login (`member`, `org`, `csrf_token`) plus
`"limits": { "max_clip_bytes": 209715200, "max_clip_s": 120, "max_clips_per_session": 3, "allowed_extensions": [".mp4", ".mov"], "wording_check": "model" }`. `wording_check` is `"model"` when `AI_CHECKER` uses a model and `"rules_only"` when `AI_CHECKER=rules`; the review screen then says "Wording check: banned-word list only" (04 deviation 18).
Errors: `unauthenticated` 401.

### 3.4 `POST /api/me/consent`

Auth: member. CSRF: yes. PRD: ORG-4.

Request (the notice text is static frontend content; the server stores the version):

```json
{ "accepted": true, "version": "2026-10-28" }
```

Response `200`: `{ "member": Member }` with `consented_at` and `consent_version` set. Idempotent (a repeat keeps the first timestamp unless `version` changed).
Errors: `validation_error` 422 (`accepted` must be `true`; `version` must equal the server's current notice version, else `details.fields[0].problem="version_mismatch"`).

## 4. Dogs

### 4.1 `GET /api/dogs`

Auth: member (any role). PRD: CAP-1, CAP-2.

Response `200`:

```json
{ "dogs": [
  { "dog": { "...Dog..." },
    "coverage": { "situations_total": 8, "situations_covered": 3 },
    "counts": { "draft_facts": 5, "confirmed_facts": 4, "sessions_in_review": 1, "clips": 3 } }
] }
```

`coverage` here is the short form (the two numbers); the full `Coverage` is in `GET /api/dogs/{id}`. Excludes `deleted` dogs. Errors: none specific.

### 4.2 `POST /api/dogs`

Auth: member. CSRF: yes. PRD: CAP-1. Limit: member write limit.

Request:

```json
{
  "name": "Biscuit",
  "sex": "male",
  "age_estimate": "about 3 years",
  "size": "medium",
  "location": "Portland, OR"
}
```

`sex`: `male | female | unknown`. `size`: `small | medium | large`. `name` 1 to 60, `age_estimate` 1 to 40, `location` optional up to 120. Photo is uploaded separately (4.5).
Response `201`: `{ "dog": Dog }` (status `draft`). Errors: `validation_error` 422.

### 4.3 `GET /api/dogs/{dog_id}`

Auth: member. PRD: CAP-2, REV-1, REV-9, REV-10 (view). Query: none.

Response `200`:

```json
{
  "dog": { "...Dog..." },
  "coverage": { "...Coverage..." },
  "checklist": { "...Checklist..." },
  "sessions": [ { "...Session...", "clip_count": 3, "ready_clip_count": 3,
                  "draft_fact_count": 4 } ],
  "clips": [ { "...Clip..." } ],
  "facts": [ { "...Fact..." } ]
}
```

`clips` holds all live (not deleted) clips of the dog across sessions, ordered by `created_at`; the dog-scope review screen uses it to attach clips to hand-added facts without per-session calls. `facts` holds all non-deleted, merged facts of the dog (draft and confirmed),
ordered by situation order, then `observed_on` desc, then `created_at`. Errors: `not_found` 404.

### 4.4 `PATCH /api/dogs/{dog_id}`

Auth: member. CSRF: yes. PRD: CAP-1.

Request: any subset of `name, sex, age_estimate, size, location` (`location: null` clears).

```json
{ "age_estimate": "about 4 years" }
```

Response `200`: `{ "dog": Dog }`. Allowed in any status except `deleted`. Editing a published dog's header fields is allowed and shows on the profile at once.
Errors: `not_found` 404, `validation_error` 422.

### 4.5 `PUT /api/dogs/{dog_id}/photo`

Auth: member. CSRF: yes. PRD: CAP-1, PUB-1.

Multipart, one field: `photo` (file). Limits: 8 MiB, `image/jpeg`, `image/png`, `image/heic` by extension and magic bytes (heic only if the decoder is present, verify). The api re-encodes to JPEG, longest side 1600 px, strips EXIF (including GPS), and stores `dogs/{id}/photo.jpg` (Pillow; verify the dependency choice).
Response `200`: `{ "dog": Dog }` with `photo_url`. Errors: `file_too_large` 413 (`max_bytes` 8388608), `unsupported_file_type` 415, `not_found` 404.

### 4.6 `PUT /api/dogs/{dog_id}/publish-checklist`

Auth: staff. CSRF: yes. PRD: REV-9, PUB-8. (Added: DESIGN had no endpoint for the checklist.)

Request:

```json
{
  "people_check": true,
  "known_concerns": "Pulls hard toward other dogs on leash.",
  "known_concerns_none": false
}
```

Rules: `known_concerns` 0 to 1000 chars (blank counts as empty); `known_concerns_none=true` requires empty `known_concerns`. Both empty and `none=false` is a valid "not filled yet" save. `people_check=true` sets `people_check_at`/`people_check_by`; `false` clears them.
Response `200`: `{ "checklist": Checklist }`.
Errors: `forbidden_role` 403, `not_found` 404, `validation_error` 422, `invalid_state` 409 (a published dog cannot clear its checklist: unpublish first). A `deleted` dog is hidden and returns `not_found`.

### 4.7 `POST /api/dogs/{dog_id}/publish`

Auth: staff. CSRF: yes. PRD: REV-5, REV-9. Body: `{}`.

Guards: dog `draft`; checklist complete (people check, concerns decision) and at least one confirmed fact. Generates `public_slug` on first publish.
Response `200`:

```json
{ "dog": { "...Dog...", "status": "published", "public_slug": "k7m2q9x4tbwe", "public_path": "/d/k7m2q9x4tbwe" },
  "public_url": "https://watchme.example.org/d/k7m2q9x4tbwe" }
```

`public_url` uses the `PUBLIC_BASE_URL` setting.
Errors: `forbidden_role` 403, `not_found` 404, `invalid_state` 409 (not `draft`), `publish_checklist_incomplete` 409 (`details.missing`).

### 4.8 `POST /api/dogs/{dog_id}/unpublish`

Auth: staff. CSRF: yes. PRD: REV-6. Body: `{}`.
Moves `published` or `adopted` to `draft`. Response `200`: `{ "dog": Dog }`. Public profile and media are 404 immediately.
Errors: `forbidden_role` 403, `not_found` 404, `invalid_state` 409.

### 4.9 `POST /api/dogs/{dog_id}/adopted`

Auth: staff. CSRF: yes. PRD: REV-6. Body: `{}`.
`draft` or `published` to `adopted`. Profile and media hidden, clips kept. Response `200`: `{ "dog": Dog }`.
Errors: `forbidden_role` 403, `not_found` 404, `invalid_state` 409.

### 4.10 `DELETE /api/dogs/{dog_id}`

Auth: staff. CSRF: yes. PRD: REV-6, NFR-8.
Starts the purge (data model 6.1). Response `202`:

```json
{ "dog_id": "d0g1...", "status": "deleted", "purge": "queued" }
```

Errors: `forbidden_role` 403, `not_found` 404 (also for an already `deleted` dog).

## 5. Sessions, clips, facts (creator side)

### 5.1 `POST /api/dogs/{dog_id}/sessions`

Auth: member. CSRF: yes. PRD: CAP-3, CAP-7. Requires consent.

Request:

```json
{
  "situations": ["leash_walk", "new_person"],
  "observed_on": "2026-10-28",
  "capture_rules_ack": true
}
```

`capture_rules_ack` must be `true` (the capture rules screen was shown and acknowledged, CAP-7). `observed_on` optional, defaults to today UTC; not later than today plus 1 day.
Response `201`: `{ "session": Session }` (`status="open"`).
Guard: the dog must be `draft`. A `published` or `adopted` dog cannot get a new session because no upload is possible there (the UI hides the action too). Errors: `consent_required` 403, `not_found` 404, `invalid_state` 409 (dog `published` or `adopted`; a `deleted` dog is hidden and returns `not_found`), `validation_error` 422 (unknown or duplicate situation, empty list, `capture_rules_ack` false).

### 5.2 `GET /api/sessions/{session_id}`

Auth: member. PRD: REV-1, CAP-8 (status polling). Query: `include=facts` (default) or `include=none` for light polling.

The UI polls this every 3 s while `session.status` is `open` with clips in `uploaded`/`processing`, or `processing`. A `review` session whose clip is being retried is `processing` and is polled the same way. It supports `If-None-Match` with a weak ETag over the response; unchanged returns `304`.

Response `200`:

```json
{
  "session": { "...Session..." },
  "clips": [ { "...Clip..." } ],
  "facts": [ { "...Fact..." } ],
  "progress": { "clips_total": 3, "clips_ready": 2, "clips_failed": 0 }
}
```

`facts` lists non-deleted, merged facts of this session (draft and confirmed), ordered by `evidence[0].clip_id` ordinal then `start_s`. Volunteers can read any session of the org; actions are role-checked separately.
Errors: `not_found` 404.

### 5.3 `POST /api/sessions/{session_id}/clips`

Auth: member (owner of the session, or staff). CSRF: yes. PRD: CAP-4, CAP-8, CAP-9. Requires consent. Limit: 20 uploads per member per hour.

Multipart (`multipart/form-data`):

| Field               | Type | Required | Notes                                                                                                                                                                       |
| ------------------- | ---- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `file`              | file | yes      | One file per request. The file name and MIME type are not trusted (iOS may send `application/octet-stream`; phone pickers send names such as `blob`, numeric names, or no extension); ffprobe decides: the container must be in the MP4/MOV family (`format_name` contains `mov` or `mp4`) and have a video stream. HEVC is accepted. The stored original keeps a client `.mp4`/`.mov` extension (case-insensitive) and otherwise gets `.mp4`. |
| `client_request_id` | text | no       | Up to 40 chars. A repeat in the same session returns the existing clip with `200` instead of creating a second one (safe retry after a dropped response).                   |

Limits: 209,715,200 bytes (200 MiB) per file; duration 120 s (0.5 s tolerance); 3 live clips per session; reverse proxy body limit must be at least 210 MiB (verify, otherwise the proxy returns its own 413). The api checks `Content-Length` before reading the body and counts streamed bytes. The file goes to `tmp/` first. Then a bounded ffprobe (10 s timeout) checks it; only on success is it moved to `dogs/{dog_id}/clips/{clip_id}/original.<ext>`, the `clip` row created, `dog.people_check_at` cleared, and the `transcode` job enqueued. A rejected upload leaves no row and no file. A probe that exceeds the 10 s bound returns `415 unsupported_file_type` with `details.reason="probe_timeout"` (no new code).

Response `201` (`200` for a repeated `client_request_id`):

```json
{ "clip": { "...Clip...", "status": "uploaded", "step": "transcode" },
  "warnings": [] }
```

`warnings` may contain `no_audio_track` (accepted; transcription will be empty).
Errors, in check order: `consent_required` 403, `not_found` 404, `not_own_session` 403, `invalid_state` 409 (session not `open`, or dog `published`/`adopted`; a `deleted` dog is hidden and returns `not_found`), `clip_limit_reached` 409, `file_too_large` 413 (`details.max_bytes`), `unsupported_file_type` 415, `upload_incomplete` 400, `clip_too_long` 422, `storage_unavailable` 503, `rate_limited` 429.

### 5.4 `POST /api/sessions/{session_id}/submit`

Auth: owner or staff. CSRF: yes. PRD: CAP-4, AI-2 (added: DESIGN had no trigger for the session merge). Requires consent. Body: `{}`.
Requires `open` and at least one live clip. Sets `processing`. Response `200`: `{ "session": Session }`. If every live clip is already terminal (`ready` or `failed`) the `merge` job is enqueued now; otherwise the last clip to finish enqueues it.
Errors: `consent_required` 403, `not_found` 404, `not_own_session` 403, `invalid_state` 409 (not `open`, or no clips).

### 5.4a `POST /api/sessions/{session_id}/retry-merge`

Auth: owner or staff. CSRF: yes. PRD: CAP-8, AI-2 (added by decision D6: a `merge_failed` session has no failed clip to retry). Body: `{}`.
Requires session `status="failed"` with `fail_code="merge_failed"`. Sets `processing`, clears `fail_code` and `review_ready_at`, and enqueues a new `merge` job (`dedupe_key=merge:{session_id}`). Idempotent while that job is live (a repeat returns the same `processing` session). Response `200`: `{ "session": Session }`.
Errors: `not_found` 404, `not_own_session` 403 (volunteer, not the filming member), `invalid_state` 409 (session is not `failed` with `merge_failed`; a session failed with `no_usable_clip` is fixed by retrying or deleting clips instead), `consent_required` 403.

### 5.5 `GET /api/clips/{clip_id}`

Auth: member. PRD: CAP-8 (single-clip status polling). Response `200`: `{ "clip": Clip }`. Errors: `not_found` 404.

### 5.6 `POST /api/clips/{clip_id}/retry`

Auth: owner or staff. CSRF: yes. PRD: CAP-8. Body: `{}`.
Allowed when `status="failed"` and `error.retryable=true` (manual retry; see 1.2). It is also allowed after the automatic retries or an immediate non-transient failure (`ai_failed`, `ai_invalid_output`). Resumes at the failed step with fresh attempts. Response `200`: `{ "clip": Clip }` (`status="processing"`).
Errors: `not_found` 404, `not_own_session` 403, `invalid_state` 409 (not failed, or not retryable: delete and re-upload instead).

### 5.7 `DELETE /api/clips/{clip_id}`

Auth: staff (any clip) or the owner when no confirmed fact cites the clip. CSRF: yes. PRD: NFR-8, CAP-8. (Added: DESIGN had no clip delete.)
Starts clip purge (data model 6.2). Response `202`: `{ "clip_id": "c11p...", "purge": "queued", "facts_deleted": 2, "facts_demoted": 1 }`.
Errors: `not_found` 404, `not_own_session` 403, `forbidden_role` 403 (volunteer, clip is cited by a confirmed fact).

### 5.8 `POST /api/facts/{fact_id}/playback-complete`

Auth: member who may review the fact (owner or staff). CSRF: yes. PRD: REV-2. Limit: member write limit.

Request (sent by the player when the range end is reached; one call per evidence row):

```json
{ "evidence_id": "e7a1...", "position_s": 21.0, "watched_s": 8.7 }
```

Server checks: `evidence_id` belongs to the fact; fact is `draft` and merged; `position_s >= end_s - 0.5`; `watched_s >= 0.8 * (end_s - start_s)`. The numbers are reported by the client; the server cannot see whether a person watched (stated limit; the draft-acceptance metric is the second guard). Upserts one `playback_event` with the current range snapshot.
Response `200`:

```json
{
  "fact_id": "f4c7...",
  "evidence_id": "e7a1...",
  "completed_at": "2026-10-28T09:12:44Z",
  "all_ranges_played": true
}
```

Errors: `not_found` 404, `not_own_session` 403, `invalid_state` 409, `validation_error` 422 (`position_s` before range end or `watched_s` too small, `problem`: `range_not_completed`).

### 5.9 `POST /api/facts/{fact_id}/confirm`

Auth: member. CSRF: yes. PRD: REV-2, REV-4, PUB-9, AI-3. Requires consent.

Request:

```json
{ "acknowledge_flags": true }
```

`acknowledge_flags` optional (default `false`); required `true` when the fact has `flags`.
Guards, in order (data model 3.4): `not_found`, `consent_required`, `invalid_state`, `staff_only_situation`, `not_own_session` (or `forbidden_role` for a session-less fact), `playback_required`, `flags_unacknowledged`, `publish_checklist_incomplete`.
Response `200`: `{ "fact": Fact }` with `status="confirmed"` and `confirmed` filled.
Errors: as listed, plus `rate_limited`.

### 5.10 `PATCH /api/facts/{fact_id}`

Auth: owner or staff. CSRF: yes. PRD: REV-2, REV-10, AI-3.

Request: any subset of `situation`, `behavior`, `evidence`. `evidence` is the full new list (0 to 3). An item with an `id` of an existing row and an unchanged range keeps that row and its playback events; others are replaced.

```json
{
  "behavior": "Walked beside the handler on a loose leash down the hallway.",
  "evidence": [
    { "id": "e7a1...", "clip_id": "c11p...", "start_s": 12.0, "end_s": 21.0 },
    { "clip_id": "c11p...", "start_s": 30.0, "end_s": 36.5 }
  ]
}
```

Effects: content change sets `origin` to `human_edited` (unless `human_added`), demotes a `confirmed` fact to `draft`, recomputes rule flags. Setting `evidence: []` on a `source=clip` or `narration` fact is rejected (`validation_error`, `problem="evidence_required"`). Allowed only when the fact is merged and not deleted.
Response `200`: `{ "fact": Fact }`.
Errors: `not_found` 404, `not_own_session` 403, `invalid_state` 409, `clip_not_ready` 409, `evidence_out_of_range` 422, `validation_error` 422.

### 5.11 `DELETE /api/facts/{fact_id}`

Auth: owner (any status) or staff. CSRF: yes. PRD: REV-2. Response `204`. Soft delete (data model F7); the fact leaves every page at once.
Errors: `not_found` 404, `not_own_session` 403.

### 5.12 `POST /api/dogs/{dog_id}/facts`

Auth: member. CSRF: yes. PRD: REV-3. Requires consent.

Request (hand-added fact; no evidence means a staff note):

```json
{
  "situation": "food_toys",
  "behavior": "Dropped the toy when asked, twice.",
  "evidence": [{ "clip_id": "c11p...", "start_s": 40.0, "end_s": 47.0 }],
  "observed_on": "2026-10-28"
}
```

`observed_on` is used only when there is no evidence (otherwise it is the session's date); default today. A volunteer may cite only clips from own sessions; staff any clip of the dog. `source` is `clip` with evidence, `staff_note` without. `origin="human_added"`, `status="draft"`.
Response `201`: `{ "fact": Fact }`. A `staff_note` can be confirmed by staff only.
Errors: `consent_required` 403, `not_found` 404, `not_own_session` 403, `clip_not_ready` 409, `evidence_out_of_range` 422, `validation_error` 422. A `deleted` dog is hidden and returns `not_found`.

## 6. Public API

No auth, no CSRF. Hidden dogs return `404 not_found` (this is the only place "hidden" is signalled; the SPA shell for `/d/{slug}` is served with `200` and renders the not-available page, ADR-0040).

### 6.1 `GET /api/public/dogs/{slug}`

PRD: PUB-0 to PUB-4, PUB-7 to PUB-9, NFR-5. Limit: 120 per IP per minute. Headers: `Cache-Control: no-store`, `X-Robots-Tag: noindex`.

The fixed safety banner (PUB-0) is not part of the response. The frontend renders
it from its own constant above the facts on every profile, so no API change can
hide it. The response carries `banner_id: "pub0_v1"` only so tests can assert the
frontend shows the banner version it expects.

Server-rendered labels (`source_label`, `confirmed_by_label`, `clip_length.label`,
`notice`) are fixed templates. `behavior` is `fact.behavior` text.

Response `200`:

```json
{
  "banner_id": "pub0_v1",
  "dog": {
    "slug": "k7m2q9x4tbwe",
    "name": "Biscuit",
    "sex": "male",
    "age_estimate": "about 3 years",
    "size": "medium",
    "location": "Portland, OR",
    "photo_url": "/media/dogs/d0g1.../photo.jpg",
    "published_at": "2026-10-28T11:00:00Z"
  },
  "org": { "name": "Maple Street Rescue", "country": "US" },
  "coverage": {
    "situations_total": 8,
    "situations_covered": 2,
    "summary": "clips in 2 of 8 situations",
    "by_situation": [
      {
        "situation": "new_person",
        "label": "Meeting a new person",
        "covered": false,
        "clip_count": 0,
        "filmed_s": 0,
        "confirmed_s": 0
      },
      {
        "situation": "leash_walk",
        "label": "Leash walk",
        "covered": true,
        "clip_count": 2,
        "filmed_s": 74,
        "confirmed_s": 16
      },
      {
        "situation": "food_toys",
        "label": "Food and toys",
        "covered": true,
        "clip_count": 1,
        "filmed_s": 31,
        "confirmed_s": 7
      }
    ]
  },
  "known_concerns": {
    "none_known": false,
    "text": "Pulls hard toward other dogs on leash."
  },
  "facts_by_situation": [
    {
      "situation": "leash_walk",
      "label": "Leash walk",
      "facts": [
        {
          "id": "f4c7...",
          "behavior": "Walked beside the handler on a loose leash for the whole hallway.",
          "source": "clip",
          "source_label": "Seen in clip",
          "observed_on": "2026-10-28",
          "confirmed_by_label": "Confirmed by volunteer",
          "clip_length": {
            "clip_count": 1,
            "seconds": 9,
            "label": "1 clip, 9 s"
          },
          "notice": null,
          "evidence": [
            {
              "clip_id": "c11p...",
              "start_s": 12.0,
              "end_s": 21.0,
              "media_url": "/media/c11p....mp4",
              "captions_url": "/media/c11p....vtt"
            }
          ]
        }
      ]
    },
    {
      "situation": "children_cats",
      "label": "Children or cats",
      "facts": [
        {
          "id": "f90a...",
          "behavior": "Looked at the shelter cat for 4 seconds and walked past.",
          "source": "clip",
          "source_label": "Seen in clip",
          "observed_on": "2026-10-27",
          "confirmed_by_label": "Confirmed by staff",
          "clip_length": {
            "clip_count": 1,
            "seconds": 4,
            "label": "1 clip, 4 s"
          },
          "notice": {
            "code": "ask_shelter_in_person_meeting",
            "text": "Ask the shelter about an in-person meeting."
          },
          "evidence": [
            {
              "clip_id": "c22q...",
              "start_s": 5.0,
              "end_s": 9.0,
              "media_url": "/media/c22q....mp4",
              "captions_url": "/media/c22q....vtt"
            }
          ]
        }
      ]
    }
  ],
  "not_observed": [
    { "situation": "new_person", "label": "Meeting a new person" },
    { "situation": "handling", "label": "Handling" }
  ],
  "contact": {
    "url": "https://example.org/adopt",
    "email": "adopt@example.org",
    "phone": null
  },
  "ask": { "enabled": true, "max_question_chars": 300, "limit_per_hour": 10 }
}
```

Rules:

- `facts_by_situation` lists situations in PRD order and omits situations with no confirmed fact. Within a group: `observed_on` desc, then `confirmed_at` desc. Only facts that pass invariant I-1 appear.
- `source_label` values: `clip` is "Seen in clip", `narration` is "Said by volunteer, not in clip", `staff_note` is "Shelter staff note". `confirmed_by_label` is "Confirmed by staff" or "Confirmed by volunteer" (no names).
- `clip_length.label`: "N clip(s), S s"; `narration` is "Narration only, S s"; `staff_note` is "No clip" (data model 4.3). `evidence` is `[]` for `staff_note`.
- A `narration` fact still carries the narrated range so a visitor can hear it; the label and `source_label` say it is not a clip of the behavior.
- `notice` is set for every `children_cats` fact (PUB-9), else `null`.
- `known_concerns`: `none_known=true` gives `text=null` (frontend shows "none known"). Shown above the facts (PUB-8); order of sections is a frontend concern: banner, header and coverage, known concerns, facts, not observed, contact, ask.
- `coverage.summary` is a convenience string; the frontend may build its own from the numbers. `by_situation` is the PUB-1 per-situation breakdown.
- `contact` is the shelter's own channel (PUB-7). There is no application form.
- Evidence `media_url` values are the only URLs the public can play (section 7).

Errors: `not_found` 404 (unknown slug, unpublished, adopted, deleted), `rate_limited` 429.

### 6.2 `POST /api/public/dogs/{slug}/ask`

PRD: QA-1, QA-2, QA-4, AI-8, QA-7. Auth none. CSRF none (needs `Content-Type: application/json`). Headers in: cookie `wm_visitor` (set if absent).

Request:

```json
{ "question": "Does he get along with other dogs?" }
```

`question`: trimmed, 3 to 300 chars, treated only as data.

Processing (the model returns ids only; the server renders every word the adopter sees):

1. Limits: 10 per hour per IP hash and per `wm_visitor`, counted from `qa_log`. Fail gives `429 rate_limited`.
2. Health check (keyword list in config, plus a model classifier only if added later): a hit returns outcome `health_redirect` and skips the model.
3. If the dog has no confirmed facts: outcome `not_observed`, no model call.
4. If today's `qa_select` spend (UTC day, from `cost_ledger`, all calls of the purpose including the first call of a request that needed two) is at or above `QA_DAILY_USD_CAP` (default 3.00 USD): `503 qa_cost_cap_reached`.
5. Selector call: the server sends the question and the dog's confirmed facts as `{ "ref": "F1", "situation": "...", "behavior": "..." }`, where `ref` is a per-request alias (F1, F2, ...). The model returns a JSON list of refs. The server maps refs back to fact ids, drops anything not in the set (counted in `qa_log.dropped_ids`), removes duplicates, and keeps at most 5 (`QA_MAX_FACTS`).
6. Render, log, respond.

Response `200`, outcome `answered`:

```json
{
  "outcome": "answered",
  "heading": "Here is what has been filmed:",
  "lines": [
    {
      "fact_id": "f4c7...",
      "text": "Walked beside the handler on a loose leash for the whole hallway.",
      "situation": "leash_walk",
      "situation_label": "Leash walk",
      "source_label": "Seen in clip",
      "observed_on": "2026-10-28",
      "confirmed_by_label": "Confirmed by volunteer",
      "clip_length": { "clip_count": 1, "seconds": 9, "label": "1 clip, 9 s" },
      "notice": null,
      "evidence": [
        {
          "clip_id": "c11p...",
          "start_s": 12.0,
          "end_s": 21.0,
          "media_url": "/media/c11p....mp4",
          "captions_url": "/media/c11p....vtt"
        }
      ]
    }
  ],
  "cited_fact_ids": ["f4c7..."],
  "limits": { "remaining_this_hour": 8 }
}
```

`text` is exactly `fact.behavior`. The frontend renders it as plain text (escaped) and plays the range when the line is tapped.

Outcome `not_observed` (empty selection, or no facts):

```json
{
  "outcome": "not_observed",
  "heading": "Not observed yet.",
  "hint": "Check the list of situations that have not been filmed, or ask the shelter.",
  "lines": [],
  "cited_fact_ids": [],
  "limits": { "remaining_this_hour": 7 }
}
```

Outcome `health_redirect`:

```json
{
  "outcome": "health_redirect",
  "heading": "Ask the shelter's vet.",
  "hint": "Health information comes from the shelter, not from these clips.",
  "lines": [],
  "cited_fact_ids": [],
  "contact": { "url": null, "email": "adopt@example.org", "phone": null },
  "limits": { "remaining_this_hour": 6 }
}
```

Headers on every `200`: `X-RateLimit-Remaining`. Errors: `not_found` 404, `question_too_short` 422, `validation_error` 422 (too long), `rate_limited` 429 (`Retry-After`), `qa_cost_cap_reached` 503, `qa_unavailable` 503.
A call that reaches processing (steps 2 to 6, including `503 qa_cost_cap_reached` and `503 qa_unavailable`) writes one `qa_log` row (`outcome=error` for the two `503`s). Calls rejected before processing (`404`, `422`, `429`) write no row, so a rejected call cannot lengthen its own lockout. Rows with `outcome=error` do not count toward the 10 per hour, so a provider outage does not use up the visitor's questions. Each model call writes one `cost_ledger` row (`purpose="qa_select"`); when a request makes two calls (the schema retry), `qa_log.ledger_id` holds the last row and both rows count toward the cap. There is no job-level retry for Q&A. The text of `heading` and `hint` comes from fixed server templates; nothing else is model-authored.

## 7. Media

Routes (all `GET`, `HEAD`):

| Route                            | Serves                                                                                                                           |
| -------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `/media/{clip_id}.mp4`           | Playback file (`dogs/{dog_id}/clips/{clip_id}/playback.mp4`), `video/mp4`                                                        |
| `/media/{clip_id}.vtt`           | WebVTT captions generated from `transcript_segment` (NFR-6), `text/vtt; charset=utf-8`. 404 when the clip has no transcript rows |
| `/media/dogs/{dog_id}/photo.jpg` | Dog photo, `image/jpeg`                                                                                                          |

Access (PRD NFR-5, PUB-3), checked in this order. Failures return `404 not_found` (never 403, so existence is not revealed):

1. The clip exists, is not soft-deleted, and has `status="ready"` (photo: dog has `photo_path`).
2. A signed-in member (valid `wm_session`) of the dog's org: allowed for any dog status except `deleted`.
3. Otherwise public: allowed only if the dog is `published` and, for clips, the clip is cited by at least one `fact_evidence` row of a `confirmed`, merged fact of that dog. Photos of a published dog are public. Clips that no confirmed fact cites (extra footage, rejected moments) are not public.

Limit stated plainly (D9, ADR-0043): the whole file of every cited clip is publicly reachable, not only the cited range. The public player plays only the cited range, but anyone with a cited clip's URL can play the full clip. The people check (REV-9) therefore applies to whole clips, and the publish dialog tells staff so. Accepted for R1; per-range clip cutting is R2.

Range behavior: served with Starlette `FileResponse`. Verified 2026-10-28 (per DESIGN): `Range: bytes=100-199` returns `206 Partial Content` with `Content-Range: bytes 100-199/SIZE`. Notes:

- `Accept-Ranges: bytes` on every response; `Content-Length` correct for the part.
- `Range: bytes=0-` or a start-only range returns `206` through the end.
- An unsatisfiable range returns `416` with `Content-Range: bytes */SIZE`.
- Multi-range requests: Starlette answers with `multipart/byteranges` in current versions (verify); browsers do not use it for `<video>`.
- `HEAD` returns headers only. Playback works on iOS Safari, which requires range support, and on Android Chrome (CAP-9; confirm on devices, verify). The transcode step writes `+faststart` MP4 so playback starts without a full download.

Headers:

| Header                   | Value                                                                                                                         |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------- |
| `Cache-Control`          | `private, no-cache` (always revalidate; unpublish or delete takes effect on the next request)                                 |
| `ETag`, `Last-Modified`  | From `FileResponse` (mtime and size); `If-None-Match` gives `304`; playback files do not change after `ready` except on retry |
| `Content-Disposition`    | `inline`                                                                                                                      |
| `X-Content-Type-Options` | `nosniff`                                                                                                                     |
| `X-Robots-Tag`           | `noindex`                                                                                                                     |
| `Vary`                   | `Cookie` (the response status depends on the cookie)                                                                          |

Already downloaded bytes cannot be recalled; deletion removes server copies only (NFR-8).
`<video>` loads send the `wm_session` cookie same-origin, so members can preview unpublished clips.
Errors: `not_found` 404, `rate_limited` 429, `416` (plain, no envelope body guarantee; the frontend does not parse it).

## 8. Operations endpoints

### 8.1 `GET /api/admin/metrics`

Auth: staff. PRD: section 8 metrics, REV-10, NFR-1, NFR-2, G1, G2. (Added: PRD metrics need a read path.)

Response `200`:

```json
{
  "as_of": "2026-10-28T14:00:00Z",
  "draft_acceptance": {
    "confirmed_ai_unchanged": 12,
    "all_drafts": 20,
    "rate": 0.6
  },
  "facts": {
    "published_dogs": 1,
    "confirmed": 14,
    "with_clip_evidence": 12,
    "clip_evidence_share": 0.857
  },
  "time": {
    "median_session_to_review_s": 212,
    "median_dog_first_session_to_publish_s": 1420
  },
  "cost": {
    "total_usd": 3.42,
    "per_dog_usd": [{ "dog_id": "d0g1...", "usd": 0.31 }],
    "qa_today_usd": 0.02,
    "qa_daily_cap_usd": 3.0
  },
  "alerts": [],
  "purge_pending": []
}
```

`draft_acceptance.all_drafts` counts AI drafts with `merged=1` in any status, deleted included. `median_session_to_review_s` uses sessions in `review` with `review_ready_at` set. `alerts` lists operator alerts, for example `ai_auth_error` after a provider `401/402/403` (04 section 8.7). Errors: `forbidden_role` 403.

### 8.2 `GET /healthz`

Auth none. `200 {"status":"ok"}` when the database answers. No dependency on AI providers.

## 9. Traceability: PRD R1 requirement to endpoint to table

Tables are from `02-data-model.md`. "Worker" means a pipeline job, not an endpoint.

| PRD ID | Endpoint(s)                                                                                                                                                 | Table(s)                                          |
| ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------- |
| ORG-0  | `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/me`; seed by `tools/seed.py` (no endpoint, by design)                                            | `org`, `member`                                   |
| ORG-4  | `POST /api/me/consent`; enforced on 5.1, 5.3, 5.4, 5.9, 5.12                                                                                                | `member`                                          |
| CAP-1  | `POST /api/dogs`, `PATCH /api/dogs/{id}`, `PUT /api/dogs/{id}/photo`, `GET /media/dogs/{id}/photo.jpg`                                                      | `dog`                                             |
| CAP-2  | `GET /api/dogs`, `GET /api/dogs/{id}`                                                                                                                       | `dog`, `fact`, `fact_evidence`, `clip`            |
| CAP-3  | `POST /api/dogs/{id}/sessions`                                                                                                                              | `session`                                         |
| CAP-4  | `POST /api/sessions/{id}/clips`, `POST /api/sessions/{id}/submit`                                                                                           | `clip`, `session`, `job`                          |
| CAP-7  | `POST /api/dogs/{id}/sessions` (`capture_rules_ack`); rules text is static frontend                                                                         | `session.rules_ack_at`                            |
| CAP-8  | Upload error codes on 5.3; `GET /api/sessions/{id}`, `GET /api/clips/{id}`, `POST /api/clips/{id}/retry`, `POST /api/sessions/{id}/retry-merge`, `DELETE /api/clips/{id}` | `clip`, `job`, `session` |
| CAP-9  | Worker `transcode`; `GET /media/{clip_id}.mp4`                                                                                                              | `clip`, `job`                                     |
| AI-1   | Worker `transcribe`; captions via `GET /media/{clip_id}.vtt`                                                                                                | `transcript_segment`, `cost_ledger`               |
| AI-2   | Worker `sample`, `draft`, `merge`; results via `GET /api/sessions/{id}`; `POST /api/sessions/{id}/submit`, `POST /api/sessions/{id}/retry-merge` | `segment`, `fact`, `fact_evidence`, `cost_ledger`, `session` |
| AI-3   | Worker `check`; flags shown in `Fact.flags`; `acknowledge_flags` on confirm                                                                                 | `fact.flags`                                      |
| AI-8   | `POST /api/public/dogs/{slug}/ask` (ref aliases, data block); worker prompts (no endpoint)                                                                  | `qa_log`                                          |
| REV-1  | `GET /api/sessions/{id}`, `GET /api/dogs/{id}`, `GET /media/{clip_id}.mp4`                                                                                  | `fact`, `fact_evidence`, `clip`                   |
| REV-2  | `POST /api/facts/{id}/playback-complete`, `POST /api/facts/{id}/confirm`, `PATCH`, `DELETE /api/facts/{id}`                                                 | `fact`, `playback_event`                          |
| REV-3  | `POST /api/dogs/{id}/facts`                                                                                                                                 | `fact`, `fact_evidence`                           |
| REV-4  | `POST /api/facts/{id}/confirm` (and edit and delete guards)                                                                                                 | `fact`, `session`                                 |
| REV-9  | `PUT /api/dogs/{id}/publish-checklist`, `POST /api/dogs/{id}/publish`                                                                                       | `dog`                                             |
| REV-5  | `POST /api/dogs/{id}/publish`, `GET /api/public/dogs/{slug}`                                                                                                | `dog`                                             |
| REV-6  | `POST .../unpublish`, `POST .../adopted`, `DELETE /api/dogs/{id}`                                                                                           | `dog`, all (purge)                                |
| REV-10 | `PATCH /api/facts/{id}` (sets origin), `GET /api/admin/metrics` (count)                                                                                     | `fact.origin`                                     |
| PUB-0  | `GET /api/public/dogs/{slug}` (`banner_id`); banner text is rendered by the frontend                                                                        | none (frontend constant)                          |
| PUB-1  | `GET /api/public/dogs/{slug}` (`dog`, `coverage`)                                                                                                           | `dog`, `clip`, `fact`, `fact_evidence`            |
| PUB-2  | `GET /api/public/dogs/{slug}` (`facts_by_situation`)                                                                                                        | `fact`, `fact_evidence`                           |
| PUB-3  | `GET /api/public/dogs/{slug}` (evidence ranges), `GET /media/{clip_id}.mp4`                                                                                 | `fact_evidence`, `clip`                           |
| PUB-4  | `GET /api/public/dogs/{slug}` (`not_observed`)                                                                                                              | derived                                           |
| PUB-7  | `GET /api/public/dogs/{slug}` (`contact`)                                                                                                                   | `org`                                             |
| PUB-8  | `PUT /api/dogs/{id}/publish-checklist`, `GET /api/public/dogs/{slug}` (`known_concerns`)                                                                    | `dog`                                             |
| PUB-9  | `POST /api/facts/{id}/confirm` (`staff_only_situation`), public `notice`                                                                                    | `fact`                                            |
| QA-1   | `POST /api/public/dogs/{slug}/ask`                                                                                                                          | `qa_log`, `cost_ledger`                           |
| QA-2   | `POST /api/public/dogs/{slug}/ask`                                                                                                                          | `fact`, `qa_log`                                  |
| QA-4   | `POST /api/public/dogs/{slug}/ask` (`health_redirect`)                                                                                                      | none (R1 has no records)                          |
| QA-7   | **No endpoint, by design**: `tools/qa_eval.py` calls the Q&A service function (the HTTP limits would block 50+ questions); asserts via `qa_log.dropped_ids` | `qa_log`                                          |
| NFR-1  | `GET /api/admin/metrics` (timing); `session.submitted_at`, `review_ready_at`                                                                                | `session`, `clip`                                 |
| NFR-2  | `GET /api/admin/metrics` (cost)                                                                                                                             | `cost_ledger`                                     |
| NFR-3  | none (frontend and CAP-9 playback)                                                                                                                          | n/a                                               |
| NFR-4  | none (English UI; transcript `lang`)                                                                                                                        | `transcript_segment`                              |
| NFR-5  | Media access rules; public 404s; no training use (config)                                                                                                   | `dog`, `clip`                                     |
| NFR-6  | `GET /media/{clip_id}.vtt` (added)                                                                                                                          | `transcript_segment`                              |
| NFR-7  | `GET /healthz`                                                                                                                                              | none                                              |
| NFR-8  | `DELETE /api/dogs/{id}`, `DELETE /api/clips/{id}`                                                                                                           | all (purge jobs)                                  |
| NFR-9  | Terms page is static frontend (`/terms`); banner is PUB-0                                                                                                   | none                                              |

R1 requirements with no API endpoint:

- QA-7 (offline runner, intentional).
- NFR-3, NFR-4, NFR-9 and the CAP-7 text are frontend or static (no API need).
- NFR-5 training opt-in: no endpoint and no schema in R1; handled by never using the contributor model (see `02-data-model.md` 6.6). This is a real, open gap for the team to confirm.
- G1 volunteer time per listing: only approximated by `GET /api/admin/metrics`; the true time includes filming, which the system cannot see. Not a defect, but the metric is partial.

## 10. Decisions and deviations from DESIGN.md v0.1

| ID  | Topic                    | DESIGN v0.1                                     | Decision here                                                                                                                                                                                                                                                                                                               | Reason                                                                             |
| --- | ------------------------ | ----------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| A1  | JSON casing              | not stated                                      | `snake_case` everywhere                                                                                                                                                                                                                                                                                                     | Matches Python and SQL names.                                                      |
| A2  | CSRF delivery            | "CSRF token on state-changing requests"         | `X-CSRF-Token` header; token derived from the cookie `sid` and returned by login and `/api/me`; no CSRF on login and public calls                                                                                                                                                                                           | Stateless; works with a signed cookie.                                             |
| A3  | Session storage          | "cookie session"                                | Signed cookie with `session_epoch` revocation; no session table                                                                                                                                                                                                                                                             | No extra table; logout revokes through the epoch.                                  |
| A4  | Added endpoints          | list in section 6                               | Added `GET /api/me`, `GET /api/dogs/{id}`, `PUT /api/dogs/{id}/photo`, `PUT .../publish-checklist`, `POST /api/sessions/{id}/submit`, `GET /api/clips/{id}`, `POST /api/clips/{id}/retry`, `DELETE /api/clips/{id}`, `GET /media/{clip_id}.vtt`, `GET /media/dogs/{id}/photo.jpg`, `GET /api/admin/metrics`, `GET /healthz` | Screens, CAP-8, NFR-6, NFR-8, and metrics need them.                               |
| A5  | Upload validation        | extension and ffprobe check                     | `Content-Length` precheck, streamed byte counter, bounded ffprobe in the api, rejection before any row; error codes per CAP-8 cause                                                                                                                                                                                         | Immediate cause and retry; no dead rows. 200 MB read as 200 MiB.                   |
| A6  | Upload idempotency       | not stated                                      | Optional `client_request_id`                                                                                                                                                                                                                                                                                                | Safe retry on weak connections (CAP-5 resumable upload is R2).                     |
| A7  | Missing audio            | "uploads clips with audio"                      | Accept with warning `no_audio_track`                                                                                                                                                                                                                                                                                        | Do not block silent but useful footage; transcript is empty.                       |
| A8  | Media for published dogs | "only for published dogs or a signed-in member" | Public only for clips cited by a confirmed fact; `404` for denials                                                                                                                                                                                                                                                          | Extra footage and rejected moments stay private.                                   |
| A9  | Media cache              | not stated                                      | `private, no-cache` with ETag                                                                                                                                                                                                                                                                                               | Unpublish and delete take effect at once. Costs a revalidation per load.           |
| A10 | Selector input           | fact ids                                        | Per-request aliases `F1..Fn` mapped to ids by the server                                                                                                                                                                                                                                                                    | Models copy 32-char hex ids badly; the allowed-set filter still applies.           |
| A11 | Not-observed text        | "matching situation if known"                   | R1 omits the matching situation                                                                                                                                                                                                                                                                                             | The selector returns refs only; adding an enum situation output is possible later. |
| A12 | Cost-cap status          | not stated                                      | `503 qa_cost_cap_reached`; health and no-facts answers still work                                                                                                                                                                                                                                                           | A cap is a service condition, not a client fault; no model cost on those paths.    |
| A13 | Pagination               | not stated                                      | None in R1                                                                                                                                                                                                                                                                                                                  | Volumes are small.                                                                 |
| A14 | Delete responses         | not stated                                      | `202` with body for dog and clip delete (async purge); `204` for fact delete                                                                                                                                                                                                                                                | Purge continues after the response.                                                |
| A15 | Checklist authority      | "needs people check and known concerns"         | Only staff set the checklist                                                                                                                                                                                                                                                                                                | The publisher attests it. Volunteers can raise concerns through staff.             |
| A16 | Publish guard            | people check and concerns                       | Also needs at least one confirmed fact                                                                                                                                                                                                                                                                                      | An empty profile is not a listing.                                                 |
| A17 | Confirm body             | none                                            | Optional `acknowledge_flags`                                                                                                                                                                                                                                                                                                | AI-3 warns without blocking; the choice is logged.                                 |
| A18 | Playback body            | none                                            | `evidence_id, position_s, watched_s` with server thresholds                                                                                                                                                                                                                                                                 | Per-range gate; basic sanity against accidental calls. Still client-reported.      |
| A19 | Hidden profile          | "returns not available"                         | Public API: `404 not_found` with the same body as an unknown slug. SPA HTML for `/d/{slug}` is served with `200` and the frontend renders "not available" (D8, ADR-0040)  | Does not reveal that a slug once existed; a static SPA host cannot know slug state. |
| A20 | Indexing                 | not stated                                      | `X-Robots-Tag: noindex` on profiles                                                                                                                                                                                                                                                                                         | No browse or search in the product.                                                |
| A21 | Coverage fields          | "clip count and seconds"                        | `clip_count`, `filmed_s`, `confirmed_s`                                                                                                                                                                                                                                                                                     | See data model D7.                                                                 |
| A22 | Clip fail codes          | five codes incl. `too_large`                    | Upload-time errors are HTTP errors; clip codes are five others (data model D8)                                                                                                                                                                                                                                              | Same reason as data model D8.                                                      |
| A23 | Photo handling           | `photo_path`                                    | Re-encode to JPEG, strip EXIF, 1600 px, in the api                                                                                                                                                                                                                                                                          | Removes GPS data from photos; no ffmpeg in the api.                                |
| A24 | Retry-merge              | not stated                                      | Added `POST /api/sessions/{id}/retry-merge` (D6)                                                                                                                                                                                                                                                                             | A `merge_failed` session has no failed clip to retry (05 open question 1).          |
| A25 | Creator media URLs       | not stated                                      | Creator `Fact.evidence[]` carries `media_url`, `captions_url` (D7)                                                                                                                                                                                                                                                          | The player never builds URLs from `clip_id` (05 open question 2).                   |
| A26 | Error and retry contract | any handler error retries                       | `JobError(code, retryable)`; transient retries only; schema-invalid output retried once in the adapter; non-transient provider errors fail at once as `ai_failed`; manual retry always possible (D2, ADR-0042)                                                                                                             | Retrying a bad request or key cannot help.                                          |
| A27 | Zero-fact clip           | not stated                                      | A clip whose drafts are all dropped is `ready` with zero facts (D4)                                                                                                                                                                                                                                                          | Empty footage is not a failure; reviewers can add facts by hand.                    |
| A28 | Q&A log and limit rules  | "every call writes one qa_log row"              | `404`/`422`/`429` write no row; `outcome=error` rows do not count toward the hourly limit; `ledger_id` is the last ledger row (03 S3, S6; 04 deviation 11)                                                                                                                                                                  | A lockout must not extend itself; an outage must not burn quota.                    |
| A29 | Cost cap default         | example `5.0`                                   | `QA_DAILY_USD_CAP` default `3.00` USD (D1, ADR-0041)                                                                                                                                                                                                                                                                         | Fits the US$150 hackathon credit.                                                   |
| A30 | New session guard        | allowed on a published dog                      | `409 invalid_state` for `published` and `adopted` dogs (D10)                                                                                                                                                                                                                                                                | A session with no possible upload is a dead end (05 X10).                           |
| A31 | Added response fields    | not stated                                      | `Session.owner_name`; `GET /api/dogs/{id}` `clips`; `GET /api/me` `limits.wording_check`; `GET /api/admin/metrics` `alerts`; flag value table; validation problem values                                                                                                                                                      | Adopted from 04 (deviation 18), 05 (open questions 4, 10, 13).                      |
| A32 | Whole-clip exposure      | not stated                                      | Whole files of cited clips are public; the public player plays only the cited range; disclosed in the publish dialog (D9, ADR-0043)                                                                                                                                                                                         | Per-range cutting is R2.                                                            |
