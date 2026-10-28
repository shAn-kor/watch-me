"""API-SED-01: `tools/seed.py` (ORG-0)."""

from __future__ import annotations

import logging

import pytest
from sqlalchemy import func, select

from app.config import Settings
from app.models import Member, Org
from app.security.passwords import PasswordHasher
from tools import seed as seed_tool

STAFF_PW = "staff-pass-Q7x!mmmm"
VOL_PW = "vol-pass-Z3k!nnnn"


@pytest.fixture
def seeded_settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={
            "seed_org_name": "Maple Street Rescue",
            "seed_org_country": "US",
            "seed_org_location": "Springfield",
            "seed_org_contact_email": "contact@maple.test",
            "seed_staff_email": "Staff@Maple.test",
            "seed_staff_password": STAFF_PW,
            "seed_volunteer_email": "vol@maple.test",
            "seed_volunteer_password": VOL_PW,
        }
    )


def _counts(session):
    return (
        session.scalar(select(func.count()).select_from(Org)),
        session.scalar(select(func.count()).select_from(Member).where(Member.role == "staff")),
        session.scalar(select(func.count()).select_from(Member).where(Member.role == "volunteer")),
    )


def test_api_sed_01_seed_twice_is_idempotent(seeded_settings, db, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    seed_tool.run(seeded_settings)
    db.expire_all()
    assert _counts(db) == (1, 1, 1)
    first = {m.email: m.password_hash for m in db.scalars(select(Member))}
    seed_tool.run(seeded_settings)
    db.expire_all()
    assert _counts(db) == (1, 1, 1)
    assert {m.email: m.password_hash for m in db.scalars(select(Member))} == first

    hasher = PasswordHasher()
    staff = db.scalar(select(Member).where(Member.role == "staff"))
    vol = db.scalar(select(Member).where(Member.role == "volunteer"))
    assert staff.email == "staff@maple.test"  # stored lower case (CHECK email_lower)
    assert staff.password_hash.startswith("$argon2id$") and vol.password_hash.startswith("$argon2")
    assert hasher.verify(staff.password_hash, STAFF_PW) and hasher.verify(vol.password_hash, VOL_PW)
    # consent is the member's own act (ORG-4), not the seed's
    assert staff.consented_at is None and vol.consented_at is None
    # no password in logs or output
    out = capsys.readouterr()
    for secret in (STAFF_PW, VOL_PW):
        assert secret not in caplog.text and secret not in out.out and secret not in out.err
    # the org has no verified flag
    assert not any("verif" in c.name for c in Org.__table__.columns)


def test_api_sed_01_missing_values_fail_without_writing(settings, db):
    incomplete = settings.model_copy(update={"seed_org_name": "Only A Name"})
    with pytest.raises(SystemExit) as exc:
        seed_tool.run(incomplete)
    assert exc.value.code not in (0, None)
    db.expire_all()
    assert _counts(db) == (0, 0, 0)


def test_api_sed_01_seeded_staff_can_log_in(seeded_settings, client, db):
    seed_tool.run(seeded_settings)
    r = client.post(
        "/api/auth/login", json={"email": "staff@maple.test", "password": STAFF_PW}
    )
    assert r.status_code == 200, r.text
    assert r.json()["member"]["role"] == "staff"


def test_api_sed_01_password_never_in_repo_files(seeded_settings):
    from pathlib import Path

    src = Path(seed_tool.__file__).read_text(encoding="utf-8")
    assert STAFF_PW not in src and VOL_PW not in src
