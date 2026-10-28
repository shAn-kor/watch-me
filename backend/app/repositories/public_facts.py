"""The one reader of facts for the public side and for Q&A (I-1, I-11, I-14).

A fact is public when it is confirmed, merged, and its dog is published. No other
module reads facts for a visitor. Evidence rows only come from clips that are
ready and not deleted.

    get_public_dog(session, slug) -> PublicDog | None        (published dogs only)
    public_facts(session, dog_id)  -> list[PublicFact]       (profile order)

Profile order: situation order (PRD 5.2), then `created_at`, then `id`. Callers
that need another order re-sort the returned list.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.situations import SITUATION_ORDER
from app.models import Clip, Dog, Fact, FactEvidence, Org, TranscriptSegment

_SITUATION_RANK = {code: i for i, code in enumerate(SITUATION_ORDER)}


@dataclass(frozen=True, slots=True)
class PublicEvidence:
    clip_id: str
    start_s: float
    end_s: float
    has_transcript: bool


@dataclass(frozen=True, slots=True)
class PublicFact:
    id: str
    dog_id: str
    situation: str
    behavior: str
    source: str
    observed_on: date
    confirmed_at: datetime
    confirmed_role: str
    created_at: datetime
    evidence: tuple[PublicEvidence, ...]


@dataclass(frozen=True, slots=True)
class PublicDog:
    id: str
    org_id: str
    name: str
    slug: str
    contact_url: str | None
    contact_email: str | None
    contact_phone: str | None


def get_public_dog(session: Session, slug: str) -> PublicDog | None:
    """The published dog with this public slug, with its shelter's contact."""
    row = session.execute(
        select(Dog, Org)
        .join(Org, Org.id == Dog.org_id)
        .where(Dog.public_slug == slug, Dog.status == "published", Dog.deleted_at.is_(None))
    ).first()
    if row is None:
        return None
    dog, org = row
    return PublicDog(
        id=dog.id,
        org_id=dog.org_id,
        name=dog.name,
        slug=dog.public_slug or slug,
        contact_url=org.contact_url,
        contact_email=org.contact_email,
        contact_phone=org.contact_phone,
    )


def public_facts(session: Session, dog_id: str) -> list[PublicFact]:
    facts = list(
        session.scalars(
            select(Fact)
            .join(Dog, Dog.id == Fact.dog_id)
            .where(
                Fact.dog_id == dog_id,
                Fact.status == "confirmed",
                Fact.merged.is_(True),
                Fact.deleted_at.is_(None),
                Dog.status == "published",
                Dog.deleted_at.is_(None),
            )
        )
    )
    facts.sort(key=lambda f: (_SITUATION_RANK.get(f.situation, 99), f.created_at, f.id))
    evidence = _evidence_by_fact(session, [f.id for f in facts])
    return [
        PublicFact(
            id=f.id,
            dog_id=f.dog_id,
            situation=f.situation,
            behavior=f.behavior,
            source=f.source,
            observed_on=f.observed_on,
            confirmed_at=f.confirmed_at,  # type: ignore[arg-type]
            confirmed_role=f.confirmed_role,  # type: ignore[arg-type]
            created_at=f.created_at,
            evidence=tuple(evidence.get(f.id, ())),
        )
        for f in facts
    ]


def _evidence_by_fact(session: Session, fact_ids: list[str]) -> dict[str, list[PublicEvidence]]:
    if not fact_ids:
        return {}
    rows = session.execute(
        select(FactEvidence, Clip.created_at)
        .join(Clip, Clip.id == FactEvidence.clip_id)
        .where(
            FactEvidence.fact_id.in_(fact_ids),
            Clip.status == "ready",
            Clip.deleted_at.is_(None),
        )
    ).all()
    clip_ids = {ev.clip_id for ev, _ in rows}
    with_transcript = (
        set(
            session.scalars(
                select(TranscriptSegment.clip_id)
                .where(TranscriptSegment.clip_id.in_(clip_ids))
                .distinct()
            )
        )
        if clip_ids
        else set()
    )
    rows.sort(key=lambda r: (r[1], r[0].start_s, r[0].id))
    out: dict[str, list[PublicEvidence]] = defaultdict(list)
    for ev, _created in rows:
        out[ev.fact_id].append(
            PublicEvidence(
                clip_id=ev.clip_id,
                start_s=ev.start_s,
                end_s=ev.end_s,
                has_transcript=ev.clip_id in with_transcript,
            )
        )
    return out
