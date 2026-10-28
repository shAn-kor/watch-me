"""Smoke tests for the Phase 0 harness itself (fixtures, seeds, app factory)."""

from __future__ import annotations

import pytest
from fastapi import APIRouter

from app.errors import NotFound
from app.main import create_app


def test_create_app_health_of_envelope(container):
    router = APIRouter()

    @router.get("/api/_probe")
    def probe():
        raise NotFound()

    app = create_app(container)
    app.include_router(router)
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        r = c.get("/api/_probe")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
    assert r.headers["X-Request-Id"]


def test_standard_world_satisfies_all_checks(seed, db):
    from sqlalchemy import func, select

    from app.models import Dog, Fact

    w = seed.standard_world()
    assert db.scalar(select(func.count()).select_from(Dog)) == 7
    assert w.dog_pub.public_slug
    assert w.dog_deleted.public_slug is None
    assert len(w.facts_review) == 6
    assert (
        db.scalar(
            select(func.count())
            .select_from(Fact)
            .where(Fact.status == "confirmed", Fact.dog_id == w.dog_pub.id)
        )
        == 5
    )


def test_foreign_keys_are_enforced(seed):
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        seed.job()  # valid: no FK
        seed.qa_log(type("D", (), {"id": "missing"})())


def test_login_as_signs_the_client_in(client, seed, login_as):
    world = seed.standard_world()
    token = login_as(world.vol1)
    r = client.get("/api/me")
    assert r.status_code == 200
    assert r.json()["member"]["id"] == world.vol1.id
    assert r.json()["csrf_token"] == token
