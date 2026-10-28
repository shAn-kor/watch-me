"""Lane S6: `repositories/public_facts.py` (I-1, I-11, I-14): the one reader of
public and Q&A facts."""

from __future__ import annotations

import pytest

from app.repositories.public_facts import get_public_dog, public_facts
from tests.api._s6_support import build_qa_world


@pytest.fixture
def world(seed):
    return build_qa_world(seed)


def test_public_facts_returns_only_confirmed_merged_facts_of_a_published_dog(db, world):
    got = public_facts(db, world.dog_a.id)
    assert [f.id for f in got] == [f.id for f in world.facts_a]  # profile order
    assert all(f.dog_id == world.dog_a.id for f in got)


def test_public_facts_hides_unmerged_and_demoted(db, seed, world):
    unmerged = seed.fact(world.dog_a, merged=False, status="draft", behavior="Unmerged.")
    demoted = seed.fact(world.dog_a, status="draft", behavior="Demoted.")
    ids = {f.id for f in public_facts(db, world.dog_a.id)}
    assert unmerged.id not in ids and demoted.id not in ids and world.draft_a.id not in ids
    assert world.deleted_a.id not in ids


@pytest.mark.parametrize("status", ["draft", "adopted", "deleted"])
def test_public_facts_empty_unless_the_dog_is_published(db, engine, world, status):
    from sqlalchemy import text

    with engine.begin() as conn:
        extra = ", public_slug = NULL" if status == "deleted" else ""
        conn.execute(
            text(f"UPDATE dog SET status = :s{extra} WHERE id = :id"),
            {"s": status, "id": world.dog_a.id},
        )
    assert public_facts(db, world.dog_a.id) == []


def test_public_facts_evidence_only_from_ready_live_clips(db, engine, seed, world):
    from sqlalchemy import text

    (first, *_) = public_facts(db, world.dog_a.id)
    assert len(first.evidence) == 1 and first.evidence[0].clip_id == world.clip_a.id
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE clip SET deleted_at = CURRENT_TIMESTAMP WHERE id = :id"),
            {"id": world.clip_a.id},
        )
    db.expire_all()
    assert public_facts(db, world.dog_a.id)[0].evidence == ()


def test_public_facts_profile_order_is_situation_then_created_at(db, seed, world):
    from datetime import UTC, datetime, timedelta

    late = seed.fact(
        world.dog_a, situation="new_person", behavior="Later new-person fact.",
        status="confirmed", confirmed_by=world.staff,
        created_at=datetime.now(UTC) + timedelta(days=1),
    )
    got = public_facts(db, world.dog_a.id)
    assert [f.id for f in got[:2]] == [world.facts_a[0].id, late.id]
    order = ["new_person", "handling", "leash_walk", "other_dog", "food_toys", "alone_time",
             "indoors_rest", "children_cats"]
    sits = [f.situation for f in got]
    assert sits == sorted(sits, key=order.index)


def test_get_public_dog_by_slug(db, seed, world):
    dog = get_public_dog(db, world.slug)
    assert dog is not None and dog.id == world.dog_a.id
    assert dog.contact_email == "adopt@example.org" and dog.contact_url is None
    assert get_public_dog(db, "zzzzzzzzzzzz") is None
    draft = seed.dog(world.org, world.staff, name="D", status="draft", public_slug="draftslug234")
    adopted = seed.dog(world.org, world.staff, name="A", status="adopted")
    assert get_public_dog(db, draft.public_slug) is None
    assert get_public_dog(db, adopted.public_slug) is None
