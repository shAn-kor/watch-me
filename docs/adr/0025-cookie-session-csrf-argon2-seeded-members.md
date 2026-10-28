# ADR-0025: Cookie session with CSRF, argon2 password hashes, seeded members

- Status: Accepted
- Date: 2026-10-28

## Context

- R1 has seeded members only (ORG-0); adopters have no account (PRD section 3).
- Creator requests change state (confirm, publish, delete) and carry role rules checked on the server (DESIGN section 6).
- Clips may show volunteers' faces and voices; privacy matters (NFR-5).

## Decision

- Passwords: argon2 hashes, seeded from environment variables, never committed.
- Session cookie: HttpOnly, Secure, SameSite=Lax; CSRF token on state-changing creator requests.
- Logs and `qa_log` store IP hashes, not raw IPs. Credentials and keys come from environment variables only.
- Upload checks: extension and ffprobe check; random file names.
- Roles in `member.role`: `staff` / `volunteer`.

## Alternatives considered

- Invite-link sign-in (SERVICE.md section 11): deferred to R2 (ORG-3).
- Token (JWT) auth: not discussed in the inputs.
- Third-party login: not discussed in the inputs.

## Consequences

- Positive: standard, small surface; no password reset flow needed in R1.
- Negative: no self-service account management; credentials rotate by re-seeding (inference).

## Related

PRD ORG-0, ORG-4; DESIGN sections 6, 9; ADR-0012.
