# Software Design: Watch Me! R1 (v0.3, 2026-10-28)

Input: PRD.md v1.3 (R1 scope only). Requirement IDs refer to the PRD.
"Verify" marks an assumption to check before relying on it.

This is the high-level design. Field-level detail lives in
`design/01-api-spec.md` and `design/02-data-model.md`; where this file and
those two differ, they win. Decisions and their reasons are in `adr/`.
v0.2 reconciles this file with 01 and 02 (their "deviations from DESIGN
v0.1" sections) and records the project lead's decisions of 2026-10-28. v0.3 lists the whole design set (section 0), applies lead decisions D1-D11 (cost cap 3.00 USD, error/retry contract, cross-clip evidence merge, SPA 404 behavior, whole-clip exposure, retry-merge) and points to `design/00-consistency-report.md` for what was reconciled. Priority when documents disagree: lead decisions, then 01, 02, 04 (AI specifics), 03, 05, 06, 07, then this file.

## 0. Detailed design documents

| Document | Content |
| -------- | ------- |
| `design/00-consistency-report.md` (written by the lead) | Conflicts found between the documents and how each was resolved; remaining open items by owner; PRD coverage checklist |
| `design/01-api-spec.md` | API specification: every endpoint, error codes, rate limits, request and response shapes, media rules |
| `design/02-data-model.md` | Data model: tables, constraints, state machines (dog, session, clip, fact, job), invariants, deletion and retention |
| `design/03-sequences.md` | Sequence diagrams of the main flows: login and consent, upload to review, failure and retry, review, publish and delete, public profile and media, Q&A |
| `design/04-ai-design.md` | AI design: provider protocols and adapters, prompts and schemas, post-processing, error mapping, cost model, evaluation |
| `design/05-screens.md` | Screens: map and navigation, range player, creator and public screens, UX copy, accessibility |
| `design/06-modules-classes.md` | Backend module tree, layering, class diagrams, method contracts, configuration settings, frontend structure |
| `design/07-test-design.md` | Test strategy, fixtures, test case catalog, traceability matrix, residual risk, definition of done |
| `adr/` | Architecture and product decision records (index: `adr/README.md`) |

## 1. Decisions

| Topic      | Decision                                                     | Why                                                            |
| ---------- | ------------------------------------------------------------ | -------------------------------------------------------------- |
| Backend    | Python 3.12, FastAPI, SQLAlchemy 2 + Alembic, Pydantic v2    | User choice; best AI and video tooling.                        |
| Frontend   | React + Vite + TypeScript SPA, mobile-first                  | Two screens sets (creator, public); simple static build.       |
| Database   | SQLite in R1 (WAL mode); Postgres-ready through SQLAlchemy   | One server, no extra service.                                  |
| Jobs       | DB-backed job table + one worker process                     | No Redis; enough for R1 volume. Error and retry contract in section 3 (ADR-0017, ADR-0042). |
| Video      | ffmpeg (transcode, audio extract, frame sampling)            | Standard; handles iPhone HEVC.                                 |
| File store | Local disk behind a `Storage` interface                      | S3-compatible store later without code changes upstream.       |
| AI         | Provider interfaces with adapters chosen by config           | Dev uses free providers; Muse models in the build for judging. |
| Deploy     | One container image, two processes (api, worker), one volume | Oracle Cloud Always Free A1 VM; fallback GCP e2-micro + Cloudflare R2 for clips (section 14). |

## 2. Architecture

```
 Phone browser (creator)        Phone browser (adopter)
          |                               |
          v                               v
  +-------------------- FastAPI (api) --------------------+
  | auth | dogs | sessions | clips | facts | publish | qa |
  | serves SPA build + clip files (HTTP Range)            |
  +----------+-------------------------+------------------+
             |                         |
         SQLite DB  <---- jobs ---->  worker process
             |                         |  ffmpeg
         Storage (volume)  <-----------+  AI providers
                                          (Transcriber, FactDrafter,
                                           WordingChecker, FactSelector)
```

- The api never runs ffmpeg or long AI calls; it enqueues jobs.
- The worker polls `jobs`, runs one pipeline step per job, and writes
  results and status back.
- Q&A (QA-2) runs inline in the api: it is one short model call.
- The api runs only a bounded `ffprobe` (metadata, 10 s timeout) on uploads
  before saving; it never transcodes (02 D9).

## 3. Processing pipeline (per clip)

| Step | Job type     | Does                                                                      | Output                                       |
| ---- | ------------ | ------------------------------------------------------------------------- | -------------------------------------------- |
| 1    | `transcode`  | ffmpeg to H.264/AAC MP4 (CAP-9); extract 16 kHz mono 16-bit WAV; probe duration| `clip.playback_path`, `clip.duration_s`      |
| 2    | `transcribe` | Transcriber on the WAV (AI-1)                                             | `transcript_segment` rows                    |
| 3    | `sample`     | Frames every k s (k = max(1, ceil(duration/48))), labeled with time; 10 s segments | frame files, `segment` rows                  |
| 4    | `draft`      | FactDrafter per clip (frames + transcript) (AI-2)                         | per-clip drafts                              |
| 4b   | `merge`      | Merges clip drafts into session facts                                     | `fact` (status draft, `merged=1`) + `fact_evidence` rows |
| 5    | `check`      | WordingChecker on each draft, once per session after the merge (AI-3)     | `fact.flags`                                 |

- Step 4 runs one model call per clip: Muse Spark accepts at most 50 images
  per request, so a 2-minute clip at 1 fps (120 frames) does not fit. With
  k as above, a 2-minute clip sends 40 frames (one every 3 s).
- Session lifecycle: `open -> processing -> review`, or `failed`. Uploads
  are accepted only in `open`. The owner calls `POST /api/sessions/{id}/submit`;
  the `merge` job runs when every live clip is `ready` or `failed`, then
  `check` runs once per session. AI drafts are `fact.merged=0` until the merge
  and are not shown in review (ADR-0035; 02 section 3.2).
- Upload-time rejection: size, type, and duration are checked before any
  clip row exists (`Content-Length` precheck, streamed byte counter, bounded
  ffprobe). These are HTTP errors, not clip failures (01 5.3; 02 D8).
- Clip failure codes (CAP-8): `unsupported_file`, `too_long`,
  `transcode_failed`, `ai_failed`, `ai_invalid_output`. `too_large` is an
  upload-time error.
- Error and retry contract (ADR-0042): AI adapters and handlers raise
  `JobError(code, retryable)`. An AI call with schema-invalid output is
  retried once inside the adapter; if still invalid the job fails at once with
  `ai_invalid_output` (not retryable). Non-transient provider errors (HTTP
  400, 401, 402, 403, 404, including image errors) fail at once as
  `ai_failed`, with no automatic retry. Job-level retries (`max_attempts`,
  backoff) apply only to transient errors: network, timeout, HTTP 429 and 5xx
  (for ffmpeg: timeout, kill, disk full). A user can still retry a failed clip
  by hand.
- The `merge` job merges duplicate facts across clips by joining their
  evidence ranges (at most 3 rows) instead of deleting one fact (ADR-0044).
  Creator fact responses carry `media_url` and `captions_url` in the public
  shape, so the player never builds URLs (01; D7).
- A clip whose drafts are all dropped by post-processing is `ready` with zero
  facts, not a failure; review tells the member to add a fact by hand.
- `session.review_ready_at` is cleared when a merge is (re)enqueued and set
  when the latest merge completes. A session in `failed` with `merge_failed`
  is retried with `POST /api/sessions/{id}/retry-merge`.
- A failed clip can be retried (`POST /api/clips/{id}/retry`, resumes at the
  failed step) or deleted. Originals, WAV, and frames are deleted once the
  clip is `ready` (02 D13).
- Clip status shown to the user: `uploaded -> processing -> ready | failed`.

### 3.1 Timestamp strategy

Two modes, chosen by config after the day-1 spike (PRD section 7):

- `frames` (default): the model sees sampled frames labeled "t=42s" plus
  the transcript with times. It must cite times that exist in its input.
  The server snaps cited ranges to the k-second frame grid and clamps them
  to the clip duration. Works with any vision model.
- `segments` (fallback): the model cites segment IDs ("clip2-seg4"); the
  server maps an ID to its 10 s range.
- `native_video` (optional): the clip file goes to a model that accepts
  video directly. Use only if the spike shows better accuracy.
  Checked 2026-10-28 (dev.meta.ai/docs/video-understanding): MP4 only;
  Chat Completions part `{"type":"video_url","video_url":{"url":..., "fps":n}}`;
  inline up to 50 MB, Files API up to 1 GiB; audio track is read with the
  frames. Timestamp output or temporal grounding is not documented, so
  `frames` stays the default.

The spike script (`tools/spike_timestamps.py`) runs a provider on 10
labeled clips and reports the share of cited ranges that contain the
labeled behavior (bar: 80%), time per session, and token cost.

## 4. AI provider layer

```python
class Transcriber(Protocol):
    def transcribe(self, wav_path: Path, lang_hint: str | None) -> list[Segment]: ...

class FactDrafter(Protocol):
    def draft(self, inp: DraftInput) -> list[DraftFact]: ...   # schema-validated

class WordingChecker(Protocol):
    def check(self, behavior: str) -> list[Flag]: ...

class FactSelector(Protocol):
    def select(self, question: str, facts: list[FactRef]) -> list[str]: ...  # fact IDs only
```

Adapters (config `AI_TRANSCRIBER`, `AI_DRAFTER`, `AI_CHECKER`,
`AI_SELECTOR`):

| Adapter           | Use                                 | Notes                                                                                                                |
| ----------------- | ----------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `mock`            | Tests, UI work, offline             | Deterministic fixtures per clip file name.                                                                           |
| `openai_compat`   | Any OpenAI-compatible endpoint      | `base_url`, `model`, `api_key`. Covers Muse Spark (`https://api.meta.ai/v1`, `muse-spark-1.3`), free dev options, and open-weight Muse Glimmer / Spark Open on any OpenAI-compatible host (availability: verify). No separate open-weight adapter (ADR-0010, ADR-0019). |
| `local_whisper`   | Free transcription in dev           | faster-whisper on CPU.                                                                                               |
| `muse_transcribe` | Muse Voice Transcribe for the build | Not OpenAI-compatible: multipart `POST /v1/asr/transcribe`, model `muse-voice-transcribe-1.0`, mode `ENDPOINTING` (turn `startMs`/`endMs`; no word timestamps). WAV mono 16-bit 16/24 kHz only; 10 min and 32 MB per request; Korean and English. $0.18/hour.                                                                                                   |
| `rules`           | WordingChecker without a model      | Banned-word list only; the model pass is a second adapter.                                                           |

Rules for every adapter:

- Structured output only: JSON validated by Pydantic. One retry inside the
  adapter with the validation error appended, then the job fails at once with
  `ai_invalid_output` (no job-level retry; section 3).
- Prompt isolation (AI-8): narration, transcripts, and adopter questions go
  inside a clearly delimited data block; the system prompt says data is
  never instructions. FactSelector output is a list of IDs, so injected
  text cannot reach the page.
- FactSelector sees per-request aliases `F1..Fn`, not fact ids; the server
  maps them back and drops anything outside the dog's confirmed set
  (ADR-0037).
- Every call writes a `cost_ledger` row (provider, model, tokens in/out,
  estimated USD in `usd_micros`, purpose) for NFR-2 and the Q&A cost cap.

Dev provider: undecided. Pick one free `openai_compat` endpoint with image
input, or run `mock` until the Meta credit arrives. Do not send real
volunteer clips to a free tier that trains on inputs.

## 5. Data model (R1)

Entities (columns, types, constraints, and state machines are in
`design/02-data-model.md`):

`org`, `member`, `dog`, `session`, `clip`, `transcript_segment`, `segment`,
`fact`, `fact_evidence`, `playback_event`, `job`, `qa_log`, `cost_ledger`.

Key rules:

- IDs of external entities are uuid4 hex strings; the public slug is 12
  random characters, not derived from the name (02 D1, D18).
- `dog.status`: `draft / published / adopted / deleted`. `fact.status`:
  `draft / confirmed / deleted`. "Published" is a dog state only; publishing
  never copies or flips facts (PRD v1.2; ADR-0005). Deleted facts are soft
  deleted until the dog is purged.
- `session.status`: `open / processing / review / failed` (section 3).
  `fact.merged` marks facts processed by the merge.
- `playback_event` is one row per evidence range and member, with a snapshot
  of the range. Editing a range removes its events and demotes the fact
  (ADR-0039).
- Hand-added facts may have no session (`staff_note`); only staff confirm
  them (02 D14).
- Coverage (PUB-1, CAP-2) is computed per situation from `source='clip'`
  facts: `clip_count`, `filmed_s` (seconds of clips with at least one
  confirmed fact), and `confirmed_s` (union of confirmed evidence ranges)
  (02 D7).
- No uploads to a `published` dog; uploading to a draft dog clears
  `people_check_at` (02 D6).
- Deleting a dog (REV-6, NFR-8) writes a tombstone first (status `deleted`,
  slug cleared, profile and media return 404), then deletes files by prefix,
  verifies, then deletes rows. The response is `202`; a failed file delete is
  retried by the purge job (ADR-0038).
- Q&A rows keep question text 30 days and rows 90 days (02 D19).

## 6. API (R1)

Full list, shapes, and error codes: `design/01-api-spec.md`. JSON is
`snake_case`; creator calls use a signed session cookie and an
`X-CSRF-Token` header (01 A2, A3).

Creator (role checked on the server):

| Area       | Endpoints                                                                                                                      | PRD                 |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------ | ------------------- |
| Auth       | `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/me`, `POST /api/me/consent`                                         | ORG-0, ORG-4        |
| Dogs       | `GET/POST /api/dogs`, `GET/PATCH /api/dogs/{id}`, `PUT /api/dogs/{id}/photo`, `PUT .../publish-checklist`                      | CAP-1, CAP-2, REV-9 |
| Sessions   | `POST /api/dogs/{id}/sessions`, `GET /api/sessions/{id}`, `POST /api/sessions/{id}/submit`, `POST /api/sessions/{id}/retry-merge` (owner or staff) | CAP-3, REV-1, CAP-8 |
| Clips      | `POST /api/sessions/{id}/clips`, `GET /api/clips/{id}`, `POST /api/clips/{id}/retry`, `DELETE /api/clips/{id}`                  | CAP-4, CAP-8        |
| Facts      | `POST /api/facts/{id}/playback-complete`, `/confirm`, `PATCH`, `DELETE /api/facts/{id}`, `POST /api/dogs/{id}/facts`           | REV-2 to REV-4, REV-10, PUB-9 |
| Publishing | `POST /api/dogs/{id}/publish` (staff; needs people check, known concerns, and at least one confirmed fact), `/unpublish`, `/adopted`, `DELETE /api/dogs/{id}` | REV-5, REV-6, REV-9 |
| Operator   | `GET /api/admin/metrics`, `GET /healthz`                                                                                       | G1 to G3, NFR-2     |

Rules worth knowing here: confirm needs a playback event for every
evidence range by that member, and `acknowledge_flags` when wording flags
exist; volunteers confirm only their own sessions; situation 8 is staff
only. The playback event is client-reported and can be forged. This is an
accepted risk: it is a review nudge, not a security control; staff publish
and the confirm-without-edit metric are the backstops (ADR-0004).

Public (no auth; profiles carry `X-Robots-Tag: noindex`):

| Method + path                      | Does                                                                                       | PRD              |
| ---------------------------------- | ------------------------------------------------------------------------------------------ | ---------------- |
| `GET /api/public/dogs/{slug}`      | Profile, coverage, facts, not-observed list, known concerns, contact. Unpublished, adopted, deleted, and unknown slugs all return the same 404 from the API; the SPA shell for `/d/{slug}` is served with 200 and renders "not available" (ADR-0040) | PUB-0 to PUB-9   |
| `GET /media/{clip_id}.mp4`, `GET /media/{clip_id}.vtt` | Playback file (Range) and captions. Public only for clips cited by a confirmed fact of a published dog; a signed-in member sees own clips; denials are 404 (ADR-0036). The whole file of a cited clip is public; the player plays only the cited range (ADR-0043) | PUB-3, NFR-5, NFR-6 |
| `GET /media/dogs/{id}/photo.jpg`   | Dog photo (re-encoded JPEG, EXIF stripped)                                                  | PUB-0            |
| `POST /api/public/dogs/{slug}/ask` | Q&A                                                                                        | QA-1, QA-2, QA-4 |

Checked 2026-10-28: Starlette 1.10.0 (FastAPI 0.162.0) `FileResponse`
answers `Range: bytes=100-199` with 206 and `Content-Range`. Use it as is;
pin `starlette>=1.10`.

## 7. Q&A flow (QA-1, QA-2, QA-4)

1. Check limits: 10 per hour per IP hash and per cookie; refuse with
   `503 qa_cost_cap_reached` when the day's Q&A spend in `cost_ledger` passes
   `QA_DAILY_USD_CAP` (default 3.00 USD per UTC day, ADR-0041; health and no-facts answers still work).
2. Health keyword or classifier hit: return the fixed health template
   ("Ask the shelter's vet."). No model call needed for the text.
3. Send the question and this dog's confirmed facts as
   `{ref, situation, behavior}` to FactSelector, where `ref` is a
   per-request alias `F1..Fn` (ADR-0037).
4. Map refs back to fact ids; keep only those that belong to this dog's
   confirmed facts; at most 5.
5. Render: empty list gives "Not observed yet." (R1 omits the matching
   situation, 01 A11); otherwise list the selected facts with clip links,
   under a fixed lead line ("Here is what has been filmed:").
6. Log to `qa_log`.

The model never writes text that reaches the adopter.

## 8. Frontend screens

Creator (`/app/...`, signed in):

1. Login, consent.
2. Dog list with coverage (CAP-2).
3. Dog detail: sessions, facts by situation, publish panel (REV-9 checklist).
4. New session in two screens: rules and situations (CAP-3, CAP-7), then
   clips and processing (upload only; no in-page recording) with per-clip
   status, retry, delete (CAP-8), submit, and retry merge. Not offered for
   published or adopted dogs.
5. Review in two scopes (per session, per dog) with the same fact cards; the
   range player plays each evidence range and posts playback-complete when
   the range has played; confirm is enabled after every range has played.
   The publish dialog says that visitors can play the whole clip (ADR-0043).
   Light theme only in R1.

Public (`/d/{slug}`):

1. Banner (PUB-0), header and coverage, known concerns.
2. Facts by situation; tap plays the range in a shared player.
3. Not observed yet list; contact block.
4. Ask box with rendered answers.

Range playback: set `currentTime = start`, play, stop at `end` with an
animation-frame check (`timeupdate` overshoots; details in
`design/05-screens.md` section 4); the playback-complete event fires once the
range counts as played (position at the end and at least 80 percent watched).

## 9. Security and privacy

- Passwords: argon2 hashes; seeded from env, never committed.
- Session cookie: HttpOnly, Secure, SameSite=Lax; CSRF token on
  state-changing creator requests.
- Upload: `Content-Length` precheck, streamed byte counter, and a bounded
  ffprobe before saving; files stored under random names; never served from
  the original path. Photos are re-encoded and EXIF is stripped.
- Media access control as in section 6 (public media only for cited clips);
  unpublished dogs return 404.
- Uploads to a published dog are blocked.
- Logs and `qa_log` store IP hashes, not raw IPs.
- Secrets from env only (`AI_API_KEY`, `SECRET_KEY`; see `design/04-ai-design.md` section 8).

## 10. Repository layout

```
watch-me/
  backend/
    app/
      main.py            # FastAPI app, routers, SPA static mount
      config.py          # settings from env
      db.py, models.py   # SQLAlchemy
      api/               # auth, dogs, sessions, facts, public
      services/          # coverage, publish rules, qa, deletion (purge)
      pipeline/          # job runner, steps (transcode, transcribe, sample, draft, merge, check)
      ai/                # protocols.py, adapters/{mock,openai_compat,local_whisper,muse_transcribe,rules}.py, prompts/
      storage.py
    worker.py
    alembic/
    tests/
  frontend/              # React + Vite + TS
  tools/
    spike_timestamps.py
    qa_eval.py           # QA-7 adversarial set runner
    seed.py              # ORG-0 seed
  eval/
    qa_adversarial.jsonl # 50+ cases
    spike_labels.jsonl   # 10 clips with labeled behavior ranges
  Dockerfile, docker-compose.yml, .env.example
```

## 11. Testing

| Level      | What                                                                        | Tool                        |
| ---------- | --------------------------------------------------------------------------- | --------------------------- |
| Unit       | Confirm rules, publish rules, coverage, range snapping, alias mapping and ID filtering in Q&A, retry rule | pytest                      |
| API        | Each endpoint with `mock` providers; role and media access checks           | pytest + httpx              |
| Pipeline   | Real ffmpeg on 2 small fixture clips (MOV HEVC, MP4)                        | pytest (marked slow)        |
| AI quality | Timestamp bar (80%)                                                         | `tools/spike_timestamps.py` |
| AI safety  | QA-7: 0 out-of-set citations; ≥95% "not observed" on no-evidence            | `tools/qa_eval.py`          |
| UI         | Creator and public flows on a phone viewport                                | manual + ego-browser check  |

## 12. Build order (maps to PRD section 7)

1. Spike: `ai/` protocols, `mock` and one real adapter, frame sampling,
   `spike_timestamps.py`. Decide `frames` or `segments`.
2. Backend core: models, migrations, seed, auth, dogs, sessions, upload,
   job runner, pipeline steps.
3. Review and publish endpoints with rules and tests.
4. Public profile and Q&A with `qa_eval.py`.
5. Frontend creator flow, then public page.
6. Container, deploy, swap in Muse adapters, measure cost (NFR-2).

## 13. Open items

- Dev AI provider (free, image input, no training on inputs). Owner: user.
- Meta key and credit for the build. Owner: user.
- Day-1 spike checks, marked "(verify)" in 04: strict-mode min/max enforcement, output-cap parameter names, cached-token reporting in `usage`, token counts, Korean ASR quality.
- Muse Spark max video duration (not documented); Spark 1.3 audio quality
  note (docs suggest 1.2 for audio).
- Open-weight hosting for `openai_compat` (Muse Glimmer / Spark Open): availability to verify.
- Host: Oracle A1 chosen (section 14); needs a non-prepaid card and A1 capacity at signup.

## 14. Hosting (checked 2026-10-28, official pricing pages)

| Option | Free limits | Fit |
| ------ | ----------- | --- |
| Oracle Cloud Always Free A1 (chosen) | Up to 2 OCPU, 12 GB RAM, 200 GB block storage, 10 TB/month outbound; always free; home region only | Full VM: Docker, ffmpeg, disk, no sleep. Needs a credit/debit card (no prepaid). Idle A1 VMs (CPU, network, memory all under 20% for 7 days) may be reclaimed. A1 capacity at signup unverified. |
| GCP e2-micro (fallback) | 1 VM in us-west1/us-central1/us-east1, 30 GB disk, 1 GB/month outbound | Outbound too small for video; serve clips from Cloudflare R2 (10 GB free, free egress). Needs a card. |
| Rejected | Render free (no persistent disk, sleeps), Railway (0.5 GB volume), Fly.io (no free tier), Hugging Face Docker Spaces (needs PRO), Koyeb (no free web service found) | |

Sources: oracle.com/cloud/free, docs.oracle.com Always Free resources,
cloud.google.com/free/docs/free-cloud-features, render.com/docs/free,
docs.railway.com pricing, fly.io/docs/about/pricing,
huggingface.co/docs/hub/spaces-overview, developers.cloudflare.com/r2/pricing.

## 15. Muse API facts (checked 2026-10-28, dev.meta.ai/docs)

- Base URL `https://api.meta.ai/v1`; OpenAI SDK works for Chat Completions
  and Responses. `muse-spark-1.3`, context 1,048,576 tokens.
- Images: max 50 per request; 50 MB inline each; only in user messages.
- Structured output: `response_format` `json_schema`, constrained decoding;
  recursive schemas rejected; `strict` defaults to false (set it true).
- Price `muse-spark-1.3`: $1.25 / 1M input, $0.15 cached, $4.25 output.
  `muse-spark-1.3-contributor` is far cheaper ($0.10 / $0.20) but Meta may
  train on the content: use only for clips with explicit opt-in (NFR-5).
- Voice Transcribe: $0.18 per audio hour.
- Doc index: https://dev.meta.ai/llms.txt (each page has a `.md` version).

## Visual refresh (2026-11-04)

The user selected Meta as the visual reference. The product-specific token
contract is in `design/09-visual-system.md`. It governs appearance while the
existing screen, API and safety contracts continue to govern behavior.
