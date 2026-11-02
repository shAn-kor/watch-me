# Watch Me!

Video-verified behavior profiles for shelter dogs. Every behavior claim links to the clip moment that shows it.

Shelter staff and volunteers upload short phone clips of a dog. Meta models draft behavior facts from the frames and the speech in each clip. A person watches the cited moment before confirming each fact. Adopters see only confirmed facts, can play the moment behind each one, and can ask questions. If no confirmed clip shows the answer, the app says "Not observed yet".

## Meta models

| Role        | Model                       | Used for                                                          |
| ----------- | --------------------------- | ----------------------------------------------------------------- |
| Transcriber | `muse-voice-transcribe-1.0` | Speech in each clip                                               |
| Drafter     | `muse-spark-1.3`            | Behavior facts with cited time ranges, from frames and transcript |
| Selector    | `muse-spark-1.3`            | Picks the confirmed facts that answer an adopter's question       |

A rule-based checker reviews drafted wording. Health questions get a redirect to a vet, not an answer.

## Run locally

You need Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22 with pnpm, ffmpeg, and a Meta Model API key.

```sh
(cd frontend && pnpm install --frozen-lockfile && pnpm build)
cd backend

export AI_API_KEY=<your Meta Model API key>
export AI_TRANSCRIBER=muse_transcribe AI_DRAFTER=openai_compat AI_CHECKER=rules AI_SELECTOR=openai_compat
export SECRET_KEY=$(openssl rand -hex 32) IP_HASH_KEY=$(openssl rand -hex 32)
export PUBLIC_BASE_URL=http://127.0.0.1:8000 COOKIE_SECURE=false PYTHONPATH=.
export SEED_ORG_NAME="Local Shelter" SEED_ORG_COUNTRY=KR SEED_ORG_LOCATION=Seoul SEED_ORG_CONTACT_EMAIL=contact@example.org
export SEED_STAFF_EMAIL=staff@example.org SEED_STAFF_PASSWORD=local-pass-12345
export SEED_VOLUNTEER_EMAIL=volunteer@example.org SEED_VOLUNTEER_PASSWORD=local-pass-67890

mkdir -p data/storage
uv run alembic upgrade head
uv run python -m tools.seed
uv run python -m app.worker &
uv run uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 and sign in as `staff@example.org` with the seed password above.

`deploy/settings.example` lists every setting. `deploy/README.md` describes a Docker and Caddy deployment.

## Tests

```sh
(cd backend && uv run pytest -q && uv run lint-imports && uv run ruff check .)
(cd frontend && pnpm test && pnpm lint && pnpm build)
```

## Docs

`docs/PRD.md` holds the product requirements. `docs/design/` holds the API, data, screen and test design, and `docs/design/08-implementation-plan.md` is the build log.
