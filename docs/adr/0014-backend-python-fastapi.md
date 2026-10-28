# ADR-0014: Backend in Python 3.12 with FastAPI, SQLAlchemy 2, Alembic, Pydantic v2

- Status: Accepted
- Date: 2026-10-28

## Context

- DESIGN section 1: "User choice; best AI and video tooling."
- The product pipeline is ffmpeg plus AI provider calls (DESIGN sections 3-4). Pydantic validates structured model output (DESIGN section 4).
- Checked 2026-10-28: Starlette 1.10.0 (FastAPI 0.162.0) FileResponse supports Range (ADR-0026).

## Decision

Python 3.12, FastAPI, SQLAlchemy 2 + Alembic, Pydantic v2. The api serves the SPA build and media; a worker process runs the pipeline (ADR-0017).

## Alternatives considered

- Next.js / Node full stack: not evaluated in the inputs; rejected by the user's choice (unverified as to technical comparison).
- Spring: not evaluated in the inputs; rejected by the user's choice (unverified as to technical comparison).

## Consequences

- Positive: one language for API, pipeline, AI adapters and eval tools (`tools/*.py`).
- Negative: frontend is a separate toolchain (ADR-0015); small team context switching.
- Follow-up: pin `starlette>=1.10`.

## Related

DESIGN sections 1, 10; ADR-0015, ADR-0016, ADR-0017, ADR-0019.
