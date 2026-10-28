"""Database constraint cases (07 section 3.6, every DB-* ID except DB-MIG-01).

Everything runs on the Alembic-migrated SQLite (the `engine` fixture copies it)
with `foreign_keys=ON`. Cases write through raw SQL and expect `IntegrityError`
unless the case says "allowed". Base rows come from `SeedBuilder`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from app.db.engine import make_engine

TS = "2026-10-28 12:00:00"


# ------------------------------------------------------------------ helpers


def run(engine: Engine, sql: str, **params):
    with engine.begin() as conn:
        return conn.execute(text(sql), params)


def rows(engine: Engine, sql: str, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).all()


def scalar(engine: Engine, sql: str, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar()


def rejected(engine: Engine, sql: str, **params) -> None:
    with pytest.raises(IntegrityError):
        run(engine, sql, **params)


def allowed(engine: Engine, sql: str, **params) -> None:
    run(engine, sql, **params)


def _upd(engine: Engine, table: str, row_id: str, sets: str, **params):
    return run(
        engine, f"UPDATE {table} SET {sets} WHERE id = :_id", _id=row_id, **params
    )


_n = 0


def _uid() -> str:
    global _n
    _n += 1
    return f"id{_n:030d}"


def insert_clip(engine: Engine, session, ordinal=1, **over):
    cols = {
        "id": _uid(),
        "session_id": session.id,
        "dog_id": session.dog_id,
        "ordinal": ordinal,
        "original_filename": "c.mp4",
        "original_size_bytes": 1000,
        "has_audio": 1,
        "duration_s": 20.0,
        "status": "ready",
        "client_request_id": None,
        "deleted_at": None,
        "fail_code": None,
    }
    cols.update(over)
    names = ", ".join(cols)
    marks = ", ".join(f":{k}" for k in cols)
    run(engine, f"INSERT INTO clip ({names}) VALUES ({marks})", **cols)
    return cols["id"]


def insert_job(engine: Engine, **over):
    cols = {"type": "transcode", "status": "queued", "dedupe_key": None}
    cols.update(over)
    names = ", ".join(cols)
    marks = ", ".join(f":{k}" for k in cols)
    run(engine, f"INSERT INTO job ({names}) VALUES ({marks})", **cols)


@pytest.fixture
def world(seed):
    org = seed.org()
    staff = seed.member(org, "staff")
    vol = seed.member(org, "volunteer")
    dog = seed.dog(org, staff)
    sess = seed.session(dog, vol)
    return type(
        "W", (), {"org": org, "staff": staff, "vol": vol, "dog": dog, "sess": sess}
    )


# ---------------------------------------------------------------------- dog


def test_db_pub_01_dog_published_check(engine, world):
    d = world.dog.id
    pub = "status='published'"
    # without slug
    rejected(
        engine,
        f"UPDATE dog SET {pub}, people_check_at=:t, known_concerns_none=1 WHERE id=:d",
        t=TS,
        d=d,
    )
    # without people_check_at
    rejected(
        engine,
        f"UPDATE dog SET {pub}, public_slug='slugaaa', known_concerns_none=1 WHERE id=:d",
        d=d,
    )
    # neither concerns nor none
    rejected(
        engine,
        f"UPDATE dog SET {pub}, public_slug='slugaaa', people_check_at=:t WHERE id=:d",
        t=TS,
        d=d,
    )
    # both concerns and none
    rejected(
        engine,
        f"UPDATE dog SET {pub}, public_slug='slugaaa', people_check_at=:t, "
        "known_concerns_none=1, known_concerns='bites' WHERE id=:d",
        t=TS,
        d=d,
    )
    assert scalar(engine, "SELECT status FROM dog WHERE id=:d", d=d) == "draft"
    # all valid
    allowed(
        engine,
        f"UPDATE dog SET {pub}, public_slug='slugaaa', people_check_at=:t, "
        "known_concerns_none=1 WHERE id=:d",
        t=TS,
        d=d,
    )
    assert scalar(engine, "SELECT status FROM dog WHERE id=:d", d=d) == "published"


def test_db_pub_02_deleted_dog_slug(engine, world):
    d = world.dog.id
    run(engine, "UPDATE dog SET public_slug='slugbbb' WHERE id=:d", d=d)
    rejected(engine, "UPDATE dog SET status='deleted' WHERE id=:d", d=d)
    allowed(
        engine,
        "UPDATE dog SET status='deleted', public_slug=NULL, deleted_at=:t WHERE id=:d",
        t=TS,
        d=d,
    )


# --------------------------------------------------------------------- fact


def _fact(seed, world, **kw):
    return seed.fact(world.dog, session=world.sess, **kw)


def test_db_fact_01_confirmed_triplet(engine, seed, world):
    f = _fact(seed, world).id
    # confirmed with a role but no time, and a time but no role
    rejected(
        engine,
        "UPDATE fact SET status='confirmed', confirmed_role='staff' WHERE id=:i",
        i=f,
    )
    rejected(
        engine,
        "UPDATE fact SET status='confirmed', confirmed_at=:t WHERE id=:i",
        i=f,
        t=TS,
    )
    rejected(engine, "UPDATE fact SET status='confirmed' WHERE id=:i", i=f)
    # draft carrying the confirm fields
    rejected(
        engine,
        "UPDATE fact SET confirmed_at=:t, confirmed_role='staff' WHERE id=:i",
        i=f,
        t=TS,
    )
    allowed(
        engine,
        "UPDATE fact SET status='confirmed', confirmed_at=:t, confirmed_role='staff' WHERE id=:i",
        i=f,
        t=TS,
    )


@pytest.mark.xfail(
    strict=True,
    reason="lead: 02 section 2.8 CHECK ((status='confirmed') = (confirmed_at IS NOT NULL AND "
    "confirmed_role IS NOT NULL)) lets a draft carry confirmed_at alone; 07 DB-FACT-01 and "
    "I-5 want it rejected. Propose adding CHECK (status = 'confirmed' OR (confirmed_at IS NULL "
    "AND confirmed_role IS NULL AND confirmed_by IS NULL))",
)
def test_db_fact_01_draft_with_confirmed_at_only(engine, seed, world):
    f = _fact(seed, world).id
    rejected(engine, "UPDATE fact SET confirmed_at=:t WHERE id=:i", i=f, t=TS)
    rejected(engine, "UPDATE fact SET confirmed_role='staff' WHERE id=:i", i=f)


def test_db_fact_02_situation_8_staff_only(engine, seed, world):
    f = _fact(seed, world, situation="children_cats").id
    rejected(
        engine,
        "UPDATE fact SET status='confirmed', confirmed_at=:t, confirmed_role='volunteer' WHERE id=:i",
        i=f,
        t=TS,
    )
    allowed(
        engine,
        "UPDATE fact SET status='confirmed', confirmed_at=:t, confirmed_role='staff' WHERE id=:i",
        i=f,
        t=TS,
    )


def test_db_fact_03_staff_note_origin(engine, seed, world):
    f = _fact(seed, world).id
    rejected(
        engine,
        "UPDATE fact SET source='staff_note', origin='ai_unchanged' WHERE id=:i",
        i=f,
    )
    allowed(
        engine,
        "UPDATE fact SET source='staff_note', origin='human_added' WHERE id=:i",
        i=f,
    )


def test_db_fact_04_unmerged_only_ai_drafts(engine, seed, world):
    f = _fact(seed, world).id
    rejected(engine, "UPDATE fact SET merged=0, origin='human_edited' WHERE id=:i", i=f)
    rejected(
        engine,
        "UPDATE fact SET merged=0, status='confirmed', confirmed_at=:t, confirmed_role='staff' "
        "WHERE id=:i",
        i=f,
        t=TS,
    )
    allowed(
        engine,
        "UPDATE fact SET merged=0, origin='ai_unchanged', status='draft' WHERE id=:i",
        i=f,
    )


def test_db_fact_05_deleted_triplet(engine, seed, world):
    f = _fact(seed, world).id
    rejected(engine, "UPDATE fact SET status='deleted' WHERE id=:i", i=f)
    rejected(engine, "UPDATE fact SET deleted_at=:t WHERE id=:i", i=f, t=TS)
    allowed(
        engine, "UPDATE fact SET status='deleted', deleted_at=:t WHERE id=:i", i=f, t=TS
    )


# ----------------------------------------------------------------- evidence


@pytest.mark.parametrize(
    ("start", "end", "ok"),
    [
        (-1.0, 3.0, False),  # start < 0
        (5.0, 5.0, False),  # end = start
        (2.0, 2.9, False),  # length 0.9
        (0.0, 60.1, False),  # length 60.1
        (2.0, 3.0, True),  # length 1.0
        (0.0, 60.0, True),  # length 60.0
    ],
)
def test_db_evd_01_evidence_range_checks(engine, seed, world, start, end, ok):
    clip = seed.clip(world.sess)
    f = _fact(seed, world).id
    sql = (
        "INSERT INTO fact_evidence (id, fact_id, clip_id, start_s, end_s) "
        "VALUES (:i, :f, :c, :s, :e)"
    )
    params = {"i": _uid(), "f": f, "c": clip.id, "s": start, "e": end}
    if ok:
        allowed(engine, sql, **params)
    else:
        rejected(engine, sql, **params)


# --------------------------------------------------------------------- clip


def test_db_clp_01_ordinal_and_live_limit(engine, seed, world):
    s = world.sess
    for n in (1, 2, 3):
        insert_clip(engine, s, n)
    # 4th live clip (ordinal 4) and ordinal 0
    with pytest.raises(IntegrityError):
        insert_clip(engine, s, 4)
    with pytest.raises(IntegrityError):
        insert_clip(engine, s, 0)
    # duplicate ordinal among live clips
    with pytest.raises(IntegrityError):
        insert_clip(engine, s, 2)
    # same ordinal as a soft-deleted clip is allowed
    run(
        engine,
        "UPDATE clip SET deleted_at=:t WHERE session_id=:s AND ordinal=3",
        t=TS,
        s=s.id,
    )
    insert_clip(engine, s, 3)
    assert scalar(engine, "SELECT count(*) FROM clip WHERE session_id=:s", s=s.id) == 4


def test_db_clp_02_clip_limits(engine, seed, world):
    s = world.sess
    with pytest.raises(IntegrityError):
        insert_clip(engine, s, 1, duration_s=120.6)
    with pytest.raises(IntegrityError):
        insert_clip(engine, s, 1, original_size_bytes=209_715_201)
    with pytest.raises(IntegrityError):
        insert_clip(engine, s, 1, status="failed", fail_code=None)
    with pytest.raises(IntegrityError):
        insert_clip(engine, s, 1, status="ready", fail_code="transcode_failed")
    # boundaries and the valid failed shape are allowed
    insert_clip(engine, s, 1, duration_s=120.5, original_size_bytes=209_715_200)
    insert_clip(engine, s, 2, status="failed", fail_code="transcode_failed")


def test_db_clp_03_client_request_id_unique_per_session(engine, seed, world):
    s = world.sess
    insert_clip(engine, s, 1, client_request_id="req-1")
    with pytest.raises(IntegrityError):
        insert_clip(engine, s, 2, client_request_id="req-1")
    # a different session accepts the same request id
    other = seed.session(world.dog, world.vol)
    insert_clip(engine, other, 1, client_request_id="req-1")
    # NULL request ids never collide
    insert_clip(engine, s, 2)
    insert_clip(engine, s, 3)


# ------------------------------------------------------------ member and org


def test_db_mem_01_consent_pair(engine, seed, world):
    m = world.vol.id
    rejected(
        engine,
        "UPDATE member SET consented_at=:t, consent_version=NULL WHERE id=:i",
        i=m,
        t=TS,
    )
    rejected(
        engine,
        "UPDATE member SET consented_at=NULL, consent_version='v1' WHERE id=:i",
        i=m,
    )
    allowed(
        engine,
        "UPDATE member SET consented_at=NULL, consent_version=NULL WHERE id=:i",
        i=m,
    )


def _insert_member(engine, org_id, email, role="volunteer"):
    run(
        engine,
        "INSERT INTO member (id, org_id, email, display_name, password_hash, role) "
        "VALUES (:i, :o, :e, 'n', 'h', :r)",
        i=_uid(),
        o=org_id,
        e=email,
        r=role,
    )


def test_db_mem_02_role_and_email_unique(engine, seed, world):
    with pytest.raises(IntegrityError):
        _insert_member(engine, world.org.id, "new@example.test", role="admin")
    _insert_member(engine, world.org.id, "dup@example.test")
    with pytest.raises(IntegrityError):
        _insert_member(engine, world.org.id, "dup@example.test")


@pytest.mark.xfail(
    strict=True,
    reason="lead: member.email is only UNIQUE on the raw value; 02 section member "
    "says 'Lowercased on write. UNIQUE' but nothing in the schema rejects 'Dup@x' vs 'dup@x'",
)
def test_db_mem_02_email_differing_in_case_is_rejected(engine, seed, world):
    _insert_member(engine, world.org.id, "case@example.test")
    with pytest.raises(IntegrityError):
        _insert_member(engine, world.org.id, "Case@Example.test")


def test_db_org_01_org_needs_a_contact(engine):
    base = (
        "INSERT INTO org (id, name, country, location, contact_url, contact_email, contact_phone) "
        "VALUES (:i, 'o', 'US', 'x', :u, :e, :p)"
    )
    rejected(engine, base, i=_uid(), u=None, e=None, p=None)
    allowed(engine, base, i=_uid(), u=None, e=None, p="010-0000-0000")


# --------------------------------------------------------------------- jobs


def test_db_job_01_dedupe_partial_unique(engine):
    insert_job(engine, dedupe_key="k1", status="queued")
    with pytest.raises(IntegrityError):
        insert_job(engine, dedupe_key="k1", status="queued")
    # one succeeded plus one queued with the same key is allowed
    insert_job(engine, dedupe_key="k2", status="succeeded")
    insert_job(engine, dedupe_key="k2", status="queued")
    # a running job also blocks a duplicate
    insert_job(engine, dedupe_key="k3", status="running")
    with pytest.raises(IntegrityError):
        insert_job(engine, dedupe_key="k3", status="queued")


def test_db_job_02_job_status_enum(engine):
    with pytest.raises(IntegrityError):
        insert_job(engine, status="weird")


def test_db_ses_01_session_and_ledger_enums(engine, seed, world):
    sid = world.sess.id
    rejected(engine, "UPDATE session SET status='weird' WHERE id=:i", i=sid)
    for ok in ("open", "processing", "review", "failed"):
        allowed(engine, "UPDATE session SET status=:s WHERE id=:i", s=ok, i=sid)

    ledger = (
        "INSERT INTO cost_ledger (purpose, provider, model) VALUES (:p, 'mock', 'mock')"
    )
    rejected(engine, ledger, p="retention")
    for ok in ("transcribe", "draft", "check", "qa_select", "spike"):
        allowed(engine, ledger, p=ok)

    qa = (
        "INSERT INTO qa_log (dog_id, ip_hash, cookie_id, outcome) "
        "VALUES (:d, 'h', 'c', :o)"
    )
    rejected(engine, qa, d=world.dog.id, o="maybe")
    for ok in ("answered", "not_observed", "health_redirect", "error"):
        allowed(engine, qa, d=world.dog.id, o=ok)


def test_db_ses_02_job_statuses_and_types(engine):
    types = (
        "transcode",
        "transcribe",
        "sample",
        "draft",
        "merge",
        "check",
        "purge_clip",
        "purge_dog",
        "retention_sweep",
    )
    for t in types:
        insert_job(engine, type=t)
    for st in ("queued", "running", "succeeded", "failed", "cancelled"):
        insert_job(engine, status=st)
    with pytest.raises(IntegrityError):
        insert_job(engine, type="weird")
    assert scalar(engine, "SELECT count(*) FROM job") == len(types) + 5


# ----------------------------------------------------------------- playback


def test_db_pbe_01_playback_unique(engine, seed, world):
    clip = seed.clip(world.sess)
    f = _fact(seed, world, clip=clip)
    ev = f.evidence[0]
    sql = (
        "INSERT INTO playback_event (fact_id, evidence_id, member_id, start_s, end_s, watched_s) "
        "VALUES (:f, :e, :m, 1.0, 4.0, 3.0)"
    )
    allowed(engine, sql, f=f.id, e=ev.id, m=world.vol.id)
    rejected(engine, sql, f=f.id, e=ev.id, m=world.vol.id)
    # another member may play the same evidence
    allowed(engine, sql, f=f.id, e=ev.id, m=world.staff.id)


# ---------------------------------------------------------------- FK / pragma


def test_db_fk_01_fk_and_cascade(engine, seed, world):
    clip = seed.clip(world.sess)
    f = _fact(seed, world, clip=clip)
    ev = f.evidence[0]
    seed.playback(f, ev, world.vol)
    ledger = seed.ledger(dog_id=world.dog.id, session_id=world.sess.id)
    seed.qa_log(world.dog)

    # member delete is restricted while rows reference it
    with pytest.raises(IntegrityError):
        run(engine, "DELETE FROM member WHERE id=:i", i=world.vol.id)
    with pytest.raises(IntegrityError):
        run(engine, "DELETE FROM org WHERE id=:i", i=world.org.id)

    # deleting the evidence row cascades its playback events only
    run(engine, "DELETE FROM fact_evidence WHERE id=:i", i=ev.id)
    assert scalar(engine, "SELECT count(*) FROM playback_event") == 0
    assert scalar(engine, "SELECT count(*) FROM fact WHERE id=:i", i=f.id) == 1
    assert scalar(engine, "SELECT count(*) FROM clip WHERE id=:i", i=clip.id) == 1

    # deleting the dog cascades sessions, clips, facts, qa_log; keeps the ledger
    run(engine, "DELETE FROM dog WHERE id=:i", i=world.dog.id)
    for table in ("session", "clip", "fact", "qa_log"):
        assert scalar(engine, f"SELECT count(*) FROM {table}") == 0, table
    row = rows(
        engine, "SELECT dog_id, session_id FROM cost_ledger WHERE id=:i", i=ledger.id
    )
    assert row == [(None, None)]
    # the members survive
    assert scalar(engine, "SELECT count(*) FROM member") == 2


def test_db_prg_01_pragmas_per_connection(settings):
    engines = [make_engine(settings.database_url) for _ in range(3)]
    try:
        for eng in engines:
            with eng.connect() as conn:
                fk = conn.exec_driver_sql("PRAGMA foreign_keys").scalar()
                jm = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
                bt = conn.exec_driver_sql("PRAGMA busy_timeout").scalar()
            assert (fk, str(jm).lower(), bt) == (1, "wal", 5000)
    finally:
        for eng in engines:
            eng.dispose()


# --------------------------------------------------------------------- UTC


def test_db_typ_01_utc_type(engine, seed, world):
    from sqlalchemy.orm import Session

    from app.models import Dog

    kst = timezone(timedelta(hours=9))
    stamp = datetime(2026, 10, 28, 21, 30, 0, tzinfo=kst)  # 12:30 UTC
    with Session(engine) as s:
        dog = s.get(Dog, world.dog.id)
        dog.adopted_at = stamp
        s.commit()

    raw = scalar(engine, "SELECT adopted_at FROM dog WHERE id=:i", i=world.dog.id)
    assert str(raw).startswith("2026-10-28 12:30:00")
    assert "+" not in str(raw)

    with Session(engine) as s:
        back = s.get(Dog, world.dog.id).adopted_at
    assert back.tzinfo is not None
    assert back.utcoffset() == timedelta(0)
    assert back == stamp

    # a naive datetime must not be stored by accident
    with Session(engine) as s:
        dog = s.get(Dog, world.dog.id)
        dog.adopted_at = datetime(2026, 10, 28, 12, 0, 0)
        with pytest.raises(Exception, match="aware"):
            s.flush()
        s.rollback()
