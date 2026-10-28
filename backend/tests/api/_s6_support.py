"""Shared helpers of the lane S6 tests (07 sections 2.2, 3.12, 3.17).

Fixtures here are imported into the test modules (`from tests.api._s6_support
import ...`), so each module can use them without a conftest of its own.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.container import AiSlots, build_container
from app.db.engine import make_session_factory
from app.domain.situations import SITUATION_ORDER
from tests.fakes import ScriptedSelector, scripted_ai_slots

QUESTION = "Does he like walks?"
URL = "/api/public/dogs/{slug}/ask"

BEHAVIORS = [
    "Walked to the visitor with a loose wagging tail.",
    "Stood still for 20 seconds while a person brushed his back.",
    "Pulled on the leash for the first minute, then walked beside the handler.",
    "Walked past two dogs behind a fence without barking.",
    "Sat and waited until the bowl was on the floor.",
    "Lay down on a bed within one minute of entering the room.",
    "Barked three times when a door slammed.",
    "Looked at the shelter cat for 4 seconds and walked past.",
]


@dataclass
class QaWorld:
    org: Any
    staff: Any
    dog_a: Any
    facts_a: list[Any]  # confirmed, profile order: facts_a[i] is alias F{i+1}
    draft_a: Any
    deleted_a: Any
    dog_b: Any
    facts_b: list[Any]
    dog_empty: Any
    clip_a: Any
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def slug(self) -> str:
        return self.dog_a.public_slug

    @property
    def ids_a(self) -> set[str]:
        return {f.id for f in self.facts_a}


def build_qa_world(seed) -> QaWorld:  # noqa: ANN001
    org = seed.org("Maple Street Rescue", contact_email="adopt@example.org")
    staff = seed.member(org, "staff", name="Staff One")

    def dog_with_facts(name: str, n: int):
        dog = seed.dog(org, staff, name=name, status="published")
        sess = seed.session(dog, staff, status="review")
        clip = seed.clip(sess, 1)
        facts = [
            seed.fact(
                dog,
                situation=SITUATION_ORDER[i % 8],
                behavior=BEHAVIORS[i % 8]
                if name == "qa_dog_a"
                else f"{name} fact {i}.",
                status="confirmed",
                session=sess,
                clip=clip,
                confirmed_by=staff,
            )
            for i in range(n)
        ]
        return dog, sess, clip, facts

    dog_a, sess_a, clip_a, facts_a = dog_with_facts("qa_dog_a", 8)
    draft_a = seed.fact(
        dog_a,
        situation="alone_time",
        behavior="Draft alone-time sentence.",
        status="draft",
        session=sess_a,
        clip=clip_a,
    )
    deleted_a = seed.fact(
        dog_a,
        situation="alone_time",
        behavior="Deleted alone-time sentence.",
        status="deleted",
        session=sess_a,
        clip=clip_a,
    )
    dog_b, _s, _c, facts_b = dog_with_facts("qa_dog_b", 6)
    dog_empty = seed.dog(org, staff, name="qa_dog_empty", status="published")
    return QaWorld(
        org=org,
        staff=staff,
        dog_a=dog_a,
        facts_a=facts_a,
        draft_a=draft_a,
        deleted_a=deleted_a,
        dog_b=dog_b,
        facts_b=facts_b,
        dog_empty=dog_empty,
        clip_a=clip_a,
    )


# ------------------------------------------------------------------ fixtures


@pytest.fixture
def qa_world(seed) -> QaWorld:  # noqa: ANN001
    return build_qa_world(seed)


@pytest.fixture
def selector() -> ScriptedSelector:
    return ScriptedSelector()


def make_container(settings, engine, clock, selector_obj, **setting_updates):  # noqa: ANN001
    updated = settings.model_copy(update={"trusted_proxy": True, **setting_updates})
    slots = scripted_ai_slots()
    slots.selector = selector_obj
    return build_container(updated, clock=clock, engine=engine, ai=slots)


@pytest.fixture
def container(settings, engine, clock, selector):  # noqa: ANN001
    """Overrides the shared `container`: trusted proxy on (so tests pick the client
    IP with X-Forwarded-For) and the scripted selector in the selector slot."""
    return make_container(settings, engine, clock, selector)


def use_selector(container, selector_obj) -> None:  # noqa: ANN001
    container.ai.selector = selector_obj
    container.services.qa_service._selector = selector_obj  # noqa: SLF001


# ------------------------------------------------------------------- helpers


def ask(
    client,
    slug: str,
    question: str = QUESTION,
    *,
    ip: str | None = None,
    cookie: str | None = None,
    **kw: Any,
):  # noqa: ANN001
    """POST the ask endpoint. `cookie=None` sends no visitor cookie."""
    client.cookies.clear()
    headers = dict(kw.pop("headers", {}))
    if ip:
        headers["X-Forwarded-For"] = ip
    if cookie:
        headers["Cookie"] = f"wm_visitor={cookie}"
    return client.post(
        URL.format(slug=slug), json={"question": question}, headers=headers, **kw
    )


def rows(engine, model, *where):  # noqa: ANN001
    with make_session_factory(engine)() as s:
        stmt = select(model)
        for w in where:
            stmt = stmt.where(w)
        return list(s.scalars(stmt.order_by(model.id)))


def code(response) -> str:  # noqa: ANN001
    return response.json()["error"]["code"]


def write_mock_selector(tmp_path: Path, **data: Any):
    """A real `MockAdapter` over a temp fixtures dir with a `default.json`."""
    from app.ai.adapters.mock import MockAdapter

    (tmp_path / "default.json").write_text(json.dumps(data), encoding="utf-8")
    return MockAdapter(tmp_path)


class CountingSelector:
    """Wraps any selector and counts provider calls."""

    def __init__(self, inner: Any):
        self.inner = inner
        self.calls = 0

    def select(self, req):  # noqa: ANN001, ANN201
        self.calls += 1
        return self.inner.select(req)


def session_of(engine) -> Session:  # noqa: ANN001
    return make_session_factory(engine)()


__all__ = [
    "AiSlots",
    "CountingSelector",
    "QaWorld",
    "ask",
    "code",
    "container",
    "make_container",
    "qa_world",
    "rows",
    "selector",
    "use_selector",
    "write_mock_selector",
    "QUESTION",
    "URL",
]
