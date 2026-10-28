# ADR-0016: SQLite (WAL) in R1, Postgres-ready through SQLAlchemy

- Status: Accepted
- Date: 2026-10-28

## Context

- DESIGN section 1: "One server, no extra service."
- R1 has one seeded org and low volume (PRD section 3). Two processes (api, worker) share the file on one volume (ADR-0027).
- Free hosting options are single VMs (DESIGN section 14).

## Decision

SQLite in WAL mode behind SQLAlchemy 2 and Alembic migrations, so a move to Postgres needs no model rewrite.

## Alternatives considered

- Postgres from the start: rejected, an extra service for R1 volume. A hosted free tier was not evaluated in the inputs.

## Consequences

- Positive: zero ops; simple backup of one file plus the storage volume.
- Negative: single-writer limits; the job table and the api share one DB (ADR-0017); concurrency limits are not measured (unverified).
- Follow-up: swap to Postgres when R2 adds many orgs.

## Related

DESIGN sections 1, 5; ADR-0014, ADR-0017, ADR-0027.
