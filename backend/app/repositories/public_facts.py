"""The one reader of facts for the public side and for Q&A (I-1, I-11, I-14).

A fact is public when it is confirmed, merged, and its dog is published. No other
module reads facts for a visitor. Evidence rows only come from clips that are
ready and not deleted.

    get_public_dog(session, slug) -> PublicDog | None        (published dogs only)
    public_facts(session, dog_id)  -> list[PublicFact]       (profile order)
    get_public_profile(session, slug) -> PublicProfileDog | None   (lane S5, header data)
    clip_is_publicly_cited(session, clip_id, dog_id) -> bool       (lane S5, media rule)
    get_media_clip / get_media_dog / transcript_cues               (lane S5, media lookups)

Profile order: situation order (PRD 5.2), then `created_at`, then `id`. Callers
that need another order re-sort the returned list.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.domain.situations import SITUATION_ORDER
from app.models import (
    Clip,
    Dog,
    Fact,
    FactEvidence,
    FilmingSession,
    Org,
    TranscriptSegment,
)

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
        select(FactEvidence, FilmingSession.created_at, Clip.ordinal)
        .join(Clip, Clip.id == FactEvidence.clip_id)
        .join(FilmingSession, FilmingSession.id == Clip.session_id)
        .where(
            FactEvidence.fact_id.in_(fact_ids),
            Clip.status == "ready",
            Clip.deleted_at.is_(None),
        )
    ).all()
    clip_ids = {r[0].clip_id for r in rows}
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
    rows.sort(key=lambda r: (r[1], r[2], r[0].start_s, r[0].id))
    out: dict[str, list[PublicEvidence]] = defaultdict(list)
    for ev, _session_at, _ordinal in rows:
        out[ev.fact_id].append(
            PublicEvidence(
                clip_id=ev.clip_id,
                start_s=ev.start_s,
                end_s=ev.end_s,
                has_transcript=ev.clip_id in with_transcript,
            )
        )
    return out


# ------------------------------------------------------------- lane S5: profile


@dataclass(frozen=True, slots=True)
class PublicProfileDog:
    """Header data of the public profile: the dog and its shelter, no member data."""

    id: str
    slug: str
    name: str
    sex: str
    age_estimate: str
    size: str
    location: str
    has_photo: bool
    published_at: datetime | None
    known_concerns_none: bool
    known_concerns: str | None
    org_name: str
    org_country: str
    contact_url: str | None
    contact_email: str | None
    contact_phone: str | None


def get_public_profile(session: Session, slug: str) -> PublicProfileDog | None:
    """The published dog with this slug, for the profile header. Same visibility
    rule as `get_public_dog`."""
    row = session.execute(
        select(Dog, Org)
        .join(Org, Org.id == Dog.org_id)
        .where(Dog.public_slug == slug, Dog.status == "published", Dog.deleted_at.is_(None))
    ).first()
    if row is None:
        return None
    dog, org = row
    return PublicProfileDog(
        id=dog.id,
        slug=dog.public_slug or slug,
        name=dog.name,
        sex=dog.sex,
        age_estimate=dog.age_estimate,
        size=dog.size,
        location=dog.location or org.location,
        has_photo=bool(dog.photo_path),
        published_at=dog.published_at,
        known_concerns_none=bool(dog.known_concerns_none),
        known_concerns=dog.known_concerns,
        org_name=org.name,
        org_country=org.country,
        contact_url=org.contact_url,
        contact_email=org.contact_email,
        contact_phone=org.contact_phone,
    )


# --------------------------------------------------------------- lane S5: media


@dataclass(frozen=True, slots=True)
class MediaClip:
    id: str
    dog_id: str
    org_id: str
    dog_status: str
    playback_path: str | None
    ready_at: datetime | None


@dataclass(frozen=True, slots=True)
class MediaDog:
    id: str
    org_id: str
    status: str
    photo_path: str | None


def get_media_clip(session: Session, clip_id: str) -> MediaClip | None:
    """A ready, not soft-deleted clip whose dog is not deleted; else `None`."""
    row = session.execute(
        select(Clip, Dog)
        .join(Dog, Dog.id == Clip.dog_id)
        .where(
            Clip.id == clip_id,
            Clip.status == "ready",
            Clip.deleted_at.is_(None),
            Dog.deleted_at.is_(None),
            Dog.status != "deleted",
        )
    ).first()
    if row is None:
        return None
    clip, dog = row
    return MediaClip(
        id=clip.id,
        dog_id=dog.id,
        org_id=dog.org_id,
        dog_status=dog.status,
        playback_path=clip.playback_path,
        ready_at=clip.ready_at,
    )


def get_media_dog(session: Session, dog_id: str) -> MediaDog | None:
    dog = session.scalars(
        select(Dog).where(Dog.id == dog_id, Dog.deleted_at.is_(None), Dog.status != "deleted")
    ).first()
    if dog is None:
        return None
    return MediaDog(id=dog.id, org_id=dog.org_id, status=dog.status, photo_path=dog.photo_path)


def clip_is_publicly_cited(session: Session, clip_id: str, dog_id: str) -> bool:
    """True when a confirmed, merged, live fact of this published dog cites the clip
    (ADR-0043). Same fact filter as `public_facts`; the range does not matter."""
    stmt = select(
        exists()
        .where(
            FactEvidence.clip_id == clip_id,
            Fact.id == FactEvidence.fact_id,
            Fact.dog_id == dog_id,
            Fact.status == "confirmed",
            Fact.merged.is_(True),
            Fact.deleted_at.is_(None),
            Dog.id == Fact.dog_id,
            Dog.status == "published",
            Dog.deleted_at.is_(None),
        )
        .correlate(None)
    )
    return bool(session.scalar(stmt))


def transcript_cues(session: Session, clip_id: str) -> list[tuple[float, float, str]]:
    """`(start_s, end_s, text)` of the clip transcript in order (empty when silent)."""
    rows = session.execute(
        select(TranscriptSegment.start_s, TranscriptSegment.end_s, TranscriptSegment.text)
        .where(TranscriptSegment.clip_id == clip_id)
        .order_by(TranscriptSegment.idx)
    ).all()
    return [(r[0], r[1], r[2]) for r in rows]
