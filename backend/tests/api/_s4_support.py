"""Shared helpers of the lane S4 API tests (07 section 3.10)."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select

from app.models import Fact, FactEvidence, PlaybackEvent
from tests.api._s1_support import csrf


class Review:
    """The `dog_review` facts of 07 section 3.10, built on top of the standard world.

    f_clip1  facts_review[0]: leash_walk, 1 range (1.0-4.0), no flags, session of vol1
    f_flag   facts_review[1]: one warn flag
    f_c8     facts_review[5]: children_cats
    f_two    two ranges on one clip
    f_note   staff_note (no session), created by staff1
    f_other  session of vol2
    """

    def __init__(self, world: Any, seed: Any):
        self.world = world
        self.seed = seed
        self.dog = world.dog_review
        self.clip = world.clips_review[0]
        self.f_clip1 = world.facts_review[0]
        self.f_flag = world.facts_review[1]
        self.f_c8 = world.facts_review[5]
        self.f_two = seed.fact(
            self.dog,
            behavior="Sniffs the visitor, then sits for a treat.",
            session=world.session_review,
            clip=self.clip,
            ranges=[(1.0, 4.0), (6.0, 9.0)],
        )
        self.f_note = seed.fact(
            self.dog,
            source="staff_note",
            behavior="Staff note: pulls less after a week.",
            created_by=world.staff1,
        )
        self.session_vol2 = seed.session(self.dog, world.vol2, status="review")
        self.clip_vol2 = seed.clip(self.session_vol2, 1)
        self.f_other = seed.fact(
            self.dog,
            behavior="Waits at the door for the handler.",
            session=self.session_vol2,
            clip=self.clip_vol2,
        )


@pytest.fixture
def world(seed):
    return seed.standard_world()


@pytest.fixture
def rv(world, seed) -> Review:
    return Review(world, seed)


def play(client, token, fact, evidence, **kw):
    body = {
        "evidence_id": evidence.id,
        "position_s": evidence.end_s,
        "watched_s": evidence.end_s - evidence.start_s,
    }
    body.update(kw)
    return client.post(
        f"/api/facts/{fact.id}/playback-complete", json=body, headers=csrf(token)
    )


def play_all(client, token, fact):
    for ev in fact.evidence:
        r = play(client, token, fact, ev)
        assert r.status_code == 200, r.text


def confirm(client, token, fact, **body):
    return client.post(f"/api/facts/{fact.id}/confirm", json=body, headers=csrf(token))


def patch(client, token, fact, **body):
    return client.patch(f"/api/facts/{fact.id}", json=body, headers=csrf(token))


def delete(client, token, fact):
    return client.delete(f"/api/facts/{fact.id}", headers=csrf(token))


def add(client, token, dog, **body):
    return client.post(f"/api/dogs/{dog.id}/facts", json=body, headers=csrf(token))


def code(response) -> str:
    return response.json()["error"]["code"]


def fresh_fact(db, fact_id: str) -> Fact:
    db.expire_all()
    return db.get(Fact, fact_id)


def evidence_rows(db, fact_id: str) -> list[FactEvidence]:
    db.expire_all()
    return list(db.scalars(select(FactEvidence).where(FactEvidence.fact_id == fact_id)))


def events(db, fact_id: str) -> list[PlaybackEvent]:
    db.expire_all()
    return list(db.scalars(select(PlaybackEvent).where(PlaybackEvent.fact_id == fact_id)))
