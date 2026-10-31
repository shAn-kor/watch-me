"""Evidence lists follow 01 section 2 order: session created_at, clip ordinal,
`start_s`, whatever the insert order or the random row ids."""

from __future__ import annotations

from datetime import timedelta

from app.db.base import new_id
from app.models import FactEvidence, FilmingSession


def _scrambled_fact(seed, dog, base_session, member, **fact_kw):
    """A fact citing clips of an earlier and a later session, rows inserted out of order."""
    now = seed.clock.now()
    early = seed.session(dog, member, status="review", created_at=now - timedelta(days=2))
    late = seed.session(dog, member, status="review", created_at=now - timedelta(days=1))
    # Created newest-session-first so clip `created_at` order differs from the 01 order.
    b1 = seed.clip(late, 1)
    a2 = seed.clip(early, 2)
    a1 = seed.clip(early, 1)
    fact = seed.fact(dog, session=base_session, **fact_kw)
    for clip, start in [(b1, 5.0), (a2, 3.0), (a1, 9.0), (a1, 2.0), (b1, 1.0)]:
        seed._add(FactEvidence(id=new_id(), fact_id=fact.id, clip_id=clip.id, start_s=start, end_s=start + 2))
    expected = [(a1.id, 2.0), (a1.id, 9.0), (a2.id, 3.0), (b1.id, 1.0), (b1.id, 5.0)]
    return fact, expected


def _pairs(evidence):
    return [(e["clip_id"], e["start_s"]) for e in evidence]


def test_session_and_dog_review_evidence_order(client, seed, login_as):
    world = seed.standard_world()
    fact, expected = _scrambled_fact(
        seed, world.dog_review, world.session_review, world.vol1
    )
    login_as(world.vol1)
    body = client.get(f"/api/sessions/{world.session_review.id}").json()
    got = next(f for f in body["facts"] if f["id"] == fact.id)
    assert _pairs(got["evidence"]) == expected

    login_as(world.staff1)
    body = client.get(f"/api/dogs/{world.dog_review.id}").json()
    facts = body["facts"] if "facts" in body else body["facts_review"]
    got = next(f for f in facts if f["id"] == fact.id)
    assert _pairs(got["evidence"]) == expected


def test_public_profile_evidence_order(client, seed, db):
    world = seed.standard_world()
    base = db.get(FilmingSession, world.facts_pub["one_range"].session_id)
    fact, expected = _scrambled_fact(
        seed, world.dog_pub, base, world.vol1, status="confirmed", confirmed_by=world.vol1
    )
    client.cookies.clear()
    body = client.get(f"/api/public/dogs/{world.dog_pub.public_slug}").json()
    flat = [f for g in body["facts_by_situation"] for f in g["facts"]]
    got = next(f for f in flat if f["id"] == fact.id)
    assert _pairs(got["evidence"]) == expected
