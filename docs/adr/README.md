# Architecture and Product Decision Records: Watch Me! (R1)

Decisions made up to 2026-10-28. Sources: SERVICE.md, PRD.md (v1.3), DESIGN.md (v0.3), design/01-api-spec.md, design/02-data-model.md, research/adoption-pain-points.md, IDEAS.md. Facts not backed by these inputs are marked "(unverified)". Contradictions between inputs are listed under "Open issues" in the relevant ADR; once decided they move to "Resolved issues". Where SERVICE.md and PRD v1.3 disagree, PRD v1.3 wins (SERVICE.md is the earlier plan).

| No. | Title | Status | Category |
| --- | ----- | ------ | -------- |
| [0001](0001-problem-video-verified-behavior-profiles.md) | Solve the missing-behavior-evidence problem with video-verified shelter dog profiles | Accepted | product |
| [0002](0002-observed-facts-only-no-labels.md) | Publish observed facts only; no personality scores or labels; eight-situation taxonomy | Accepted | product |
| [0003](0003-not-a-behavior-or-safety-assessment.md) | Position the product as not a behavior or safety assessment | Accepted | product |
| [0004](0004-human-confirms-every-fact-playback-gate.md) | A human confirms every fact; confirm is enabled only after the clip range plays to the end | Accepted | product |
| [0005](0005-staff-publishes.md) | Staff publishes; volunteer-confirmed facts still need a staff publish | Accepted | product |
| [0006](0006-no-adoption-applications-in-app.md) | No adoption applications in the app; contact goes through the shelter's own channel | Accepted | product |
| [0007](0007-discovery-by-shared-link.md) | Discovery by shared link; no search or browse screen in R1 | Accepted | product |
| [0008](0008-adopted-dogs-hidden-clips-kept.md) | Adopted dogs are hidden and clips kept; delete removes files | Accepted | product |
| [0009](0009-markets-us-korea-r1-english-facing.md) | Target US and Korea, but R1 is English-facing; Korean UI and bilingual profiles in R2 | Accepted | product |
| [0010](0010-nonprofit-model-and-cost-per-listing.md) | Nonprofit model, very low cost per listing, contributor pricing only with opt-in | Accepted | product |
| [0011](0011-single-name-watch-me.md) | One name, "Watch Me!", for both markets | Accepted | product |
| [0012](0012-r1-scope-one-seeded-path.md) | Cut R1 to one seeded end-to-end path; no sign-up or organization verification | Accepted | product |
| [0013](0013-outdated-fact-marker-90-days.md) | Facts older than 90 days show "may be outdated" (R2) | Accepted | product |
| [0014](0014-backend-python-fastapi.md) | Backend in Python 3.12 with FastAPI, SQLAlchemy 2, Alembic, Pydantic v2 | Accepted | technical |
| [0015](0015-frontend-react-vite-spa.md) | React + Vite + TypeScript SPA, mobile-first | Accepted | technical |
| [0016](0016-sqlite-wal-postgres-ready.md) | SQLite (WAL) in R1, Postgres-ready through SQLAlchemy | Accepted | technical |
| [0017](0017-db-job-table-single-worker.md) | DB-backed job table with one worker process | Accepted | technical |
| [0018](0018-local-disk-storage-interface.md) | Local disk storage behind a `Storage` interface | Accepted | technical |
| [0019](0019-ai-provider-abstraction.md) | AI provider abstraction with four interfaces and config-chosen adapters | Accepted | technical |
| [0020](0020-timestamp-strategy.md) | Timestamp strategy: labeled frames by default, 10 s segments as fallback, native video optional | Accepted | technical |
| [0021](0021-frame-sampling-interval-one-call-per-clip.md) | Frame interval k = max(1, ceil(duration/48)) and one model call per clip | Accepted | technical |
| [0022](0022-qa-model-returns-fact-ids-only.md) | Q&A: the model returns fact IDs only; the server renders all text | Accepted | technical |
| [0023](0023-prompt-isolation.md) | Prompt isolation for narration and adopter questions | Accepted | technical |
| [0024](0024-muse-voice-transcribe-for-narration.md) | Muse Voice Transcribe for narration in the build; local Whisper for development | Accepted | technical |
| [0025](0025-cookie-session-csrf-argon2-seeded-members.md) | Cookie session with CSRF, argon2 password hashes, seeded members | Accepted | technical |
| [0026](0026-media-served-with-starlette-range.md) | Serve media with Starlette FileResponse and HTTP Range | Accepted | technical |
| [0027](0027-single-container-oracle-a1-hosting.md) | One container, two processes, one volume; Oracle Cloud Always Free A1, fallback GCP e2-micro + Cloudflare R2 | Accepted | technical |
| [0028](0028-separate-git-repo-for-submission.md) | Separate git repository `watch-me/` for the public submission | Accepted | technical |
| [0029](0029-day1-timestamp-spike-80-percent-bar.md) | Day-1 timestamp spike with an 80% bar before building on timestamps | Accepted | technical |
| [0030](0030-ffmpeg-transcode-and-clip-limits.md) | ffmpeg transcode to H.264 MP4 and fixed clip limits | Accepted | technical |
| [0031](0031-mobile-web-only-no-native-app.md) | Mobile web only; no native app | Accepted | product |
| [0032](0032-capture-rules-consent-no-third-parties.md) | Capture rules, member consent, and no third parties in frame | Accepted | product |
| [0033](0033-cost-ledger-and-qa-daily-cost-cap.md) | Cost ledger for every AI call and a daily cost cap on Q&A | Accepted | technical |
| [0034](0034-positioning-video-to-evidence-not-simple-rag.md) | Lead with video-to-timestamped-evidence; Q&A is a constrained lookup, not free chat | Accepted | product |
| [0035](0035-session-lifecycle-explicit-submit-merge-job.md) | Session lifecycle with an explicit submit and a merge job | Accepted | technical |
| [0036](0036-public-media-only-for-cited-clips.md) | Public media only for clips cited by a confirmed fact | Accepted | technical |
| [0037](0037-qa-per-request-aliases.md) | Q&A sends per-request aliases F1..Fn instead of fact IDs | Accepted | technical |
| [0038](0038-tombstone-deletion-order.md) | Delete by tombstone first, then files, then rows | Accepted | technical |
| [0039](0039-playback-event-per-evidence-range.md) | One playback event per evidence range, snapshotted | Accepted | technical |
| [0040](0040-spa-200-public-api-404-for-hidden-profiles.md) | SPA shell returns 200; the public API returns 404 for hidden profiles | Accepted | technical |
| [0041](0041-qa-daily-cost-cap-3-usd.md) | Q&A daily cost cap defaults to 3.00 USD | Accepted | technical |
| [0042](0042-job-error-retryable-contract.md) | JobError carries a retryable flag; retry only transient errors | Accepted | technical |
| [0043](0043-whole-clip-exposure-accepted-r1.md) | Whole files of cited clips are public in R1; per-range cutting is R2 | Accepted | technical |
| [0044](0044-cross-clip-evidence-merge.md) | Merge duplicate facts across clips by joining evidence | Accepted | technical |

## How to add an ADR

1. Copy the structure of any existing ADR: Title, Status, Date, Context, Decision, Alternatives considered, Consequences, Related (add Open issues when inputs disagree).
2. Use the next free number and a kebab-case file name: `NNNN-short-title.md`. Numbers are never reused.
3. Status is `Proposed` until accepted, then `Accepted`. To change a decision, write a new ADR and mark the old one `Superseded by ADR-NNNN`; do not rewrite history.
4. Cite the source file, section or URL for each fact. Mark anything without a source "(unverified)". Do not invent numbers.
5. Keep it under about 60 lines. Add a row to the table above.
