"""Seed the one org, one staff member and one volunteer (ORG-0, 06 section 9).

    python -m tools.seed

Reads `SEED_ORG_*`, `SEED_STAFF_EMAIL`, `SEED_STAFF_PASSWORD`,
`SEED_VOLUNTEER_EMAIL` and `SEED_VOLUNTEER_PASSWORD` through `Settings`. Passwords
are hashed with argon2id and never printed or logged. Safe to run again: rows that
exist (org by name, member by email) are left as they are, so a changed password in
the environment does not overwrite a member's password. Members have not consented
yet; they accept the consent screen on first login (ORG-4). The org has no
"verified" flag in R1 (PRD ORG-0).
"""

from __future__ import annotations

import sys

from sqlalchemy import select

from app.config import Settings
from app.db.base import new_id
from app.db.engine import make_engine, make_session_factory
from app.models import Member, Org
from app.security.passwords import PasswordHasher

_REQUIRED = (
    "seed_org_name",
    "seed_org_country",
    "seed_org_location",
    "seed_staff_email",
    "seed_staff_password",
    "seed_volunteer_email",
    "seed_volunteer_password",
)
_CONTACTS = ("seed_org_contact_url", "seed_org_contact_email", "seed_org_contact_phone")


def _value(settings: Settings, name: str) -> str | None:
    raw = getattr(settings, name)
    if raw is None:
        return None
    text = raw.get_secret_value() if hasattr(raw, "get_secret_value") else str(raw)
    return text.strip() or None


def _problems(settings: Settings) -> list[str]:
    missing = [n.upper() for n in _REQUIRED if _value(settings, n) is None]
    if all(_value(settings, n) is None for n in _CONTACTS):
        missing.append("one of SEED_ORG_CONTACT_URL, SEED_ORG_CONTACT_EMAIL, SEED_ORG_CONTACT_PHONE")
    country = _value(settings, "seed_org_country")
    if country is not None and len(country) != 2:
        missing.append("SEED_ORG_COUNTRY (two letters)")
    return missing


def run(settings: Settings) -> dict[str, str]:
    """Create what is missing. Returns what happened per item (`created` or `exists`)."""
    problems = _problems(settings)
    if problems:
        raise SystemExit("seed: missing or invalid settings: " + "; ".join(problems))
    hasher = PasswordHasher()
    engine = make_engine(settings.database_url)
    result: dict[str, str] = {}
    try:
        with make_session_factory(engine)() as session:
            name = _value(settings, "seed_org_name")
            org = session.scalar(select(Org).where(Org.name == name))
            result["org"] = "exists"
            if org is None:
                org = Org(
                    id=new_id(),
                    name=name,
                    country=(_value(settings, "seed_org_country") or "").upper(),
                    location=_value(settings, "seed_org_location"),
                    contact_url=_value(settings, "seed_org_contact_url"),
                    contact_email=_value(settings, "seed_org_contact_email"),
                    contact_phone=_value(settings, "seed_org_contact_phone"),
                )
                session.add(org)
                session.flush()
                result["org"] = "created"
            for role in ("staff", "volunteer"):
                email = (_value(settings, f"seed_{role}_email") or "").lower()
                result[role] = "exists"
                if session.scalar(select(Member).where(Member.email == email)) is not None:
                    continue
                session.add(
                    Member(
                        id=new_id(),
                        org_id=org.id,
                        email=email,
                        display_name=email.split("@")[0][:80],
                        password_hash=hasher.hash(_value(settings, f"seed_{role}_password") or ""),
                        role=role,
                    )
                )
                result[role] = "created"
            session.commit()
    finally:
        engine.dispose()
    return result


def main() -> int:
    settings = Settings()  # type: ignore[call-arg]
    result = run(settings)
    for item, state in result.items():
        print(f"seed: {item} {state}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
