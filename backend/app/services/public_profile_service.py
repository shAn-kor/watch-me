"""PublicProfileService (06 section 3.8; 01 section 6.1, PUB-0 to PUB-9).

Builds the public profile of a published dog. Facts come only from
`repositories.public_facts` (I-1, UT-ARCH-02). Labels come from `domain.labels`; the
view carries no member names, ids of members, IPs or file paths (NFR-5).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from app.config import Settings
from app.db.uow import UnitOfWork
from app.domain.coverage import SituationCoverage
from app.domain.labels import ClipLength, clip_length, confirmed_by_label, source_label
from app.domain.ranges import Range
from app.domain.situations import SITUATION_LABELS, SITUATION_ORDER
from app.errors import NotFound
from app.repositories.public_facts import PublicFact, get_public_profile, public_facts
from app.services import qa_templates as t
from app.services.coverage_service import CoverageService
from app.services.views import MediaUrls

BANNER_ID = "pub0_v1"


@dataclass(frozen=True, slots=True)
class ProfileDog:
    slug: str
    name: str
    sex: str
    age_estimate: str
    size: str
    location: str
    photo_url: str | None
    published_at: datetime | None


@dataclass(frozen=True, slots=True)
class ProfileEvidence:
    clip_id: str
    start_s: float
    end_s: float
    media_url: str
    captions_url: str | None


@dataclass(frozen=True, slots=True)
class ProfileNotice:
    code: str
    text: str


@dataclass(frozen=True, slots=True)
class ProfileFact:
    id: str
    behavior: str
    source: str
    source_label: str
    observed_on: date
    confirmed_by_label: str
    clip_length: ClipLength
    notice: ProfileNotice | None
    evidence: tuple[ProfileEvidence, ...]


@dataclass(frozen=True, slots=True)
class ProfileGroup:
    situation: str
    label: str
    facts: tuple[ProfileFact, ...]


@dataclass(frozen=True, slots=True)
class ProfileCoverage:
    situations_total: int
    situations_covered: int
    summary: str
    by_situation: tuple[SituationCoverage, ...]


@dataclass(frozen=True, slots=True)
class ProfileConcerns:
    none_known: bool
    text: str | None


@dataclass(frozen=True, slots=True)
class ProfileContact:
    url: str | None
    email: str | None
    phone: str | None


@dataclass(frozen=True, slots=True)
class ProfileAsk:
    enabled: bool
    max_question_chars: int
    limit_per_hour: int


@dataclass(frozen=True, slots=True)
class NotObserved:
    situation: str
    label: str


@dataclass(frozen=True, slots=True)
class PublicProfile:
    banner_id: str
    dog: ProfileDog
    org_name: str
    org_country: str
    coverage: ProfileCoverage
    known_concerns: ProfileConcerns
    facts_by_situation: tuple[ProfileGroup, ...]
    not_observed: tuple[NotObserved, ...]
    contact: ProfileContact
    ask: ProfileAsk


class PublicProfileService:
    def __init__(self, *, settings: Settings, media_urls: MediaUrls, coverage: CoverageService):
        self._settings = settings
        self._media = media_urls
        self._coverage = coverage

    def get_profile(self, uow: UnitOfWork, slug: str) -> PublicProfile:
        """The profile of the published dog with this slug, else `not_found`
        (the same for an unknown, unpublished, adopted or deleted dog)."""
        session = uow.session
        dog = get_public_profile(session, slug)
        if dog is None:
            raise NotFound()
        facts = public_facts(session, dog.id)
        coverage = self._coverage.for_dog(uow, dog.id)

        by_situation: dict[str, list[PublicFact]] = {}
        for fact in facts:
            by_situation.setdefault(fact.situation, []).append(fact)
        groups = tuple(
            ProfileGroup(
                situation=situation,
                label=SITUATION_LABELS[situation],
                facts=tuple(
                    self._fact(f)
                    for f in sorted(
                        by_situation[situation],
                        key=lambda f: (f.observed_on, f.confirmed_at),
                        reverse=True,
                    )
                ),
            )
            for situation in SITUATION_ORDER
            if situation in by_situation
        )
        covered = coverage.situations_covered
        return PublicProfile(
            banner_id=BANNER_ID,
            dog=ProfileDog(
                slug=dog.slug,
                name=dog.name,
                sex=dog.sex,
                age_estimate=dog.age_estimate,
                size=dog.size,
                location=dog.location,
                photo_url=self._media.dog_photo(dog.id, has_photo=dog.has_photo),
                published_at=dog.published_at,
            ),
            org_name=dog.org_name,
            org_country=dog.org_country,
            coverage=ProfileCoverage(
                situations_total=coverage.situations_total,
                situations_covered=covered,
                summary=f"clips in {covered} of {coverage.situations_total} situations",
                by_situation=coverage.entries,
            ),
            known_concerns=ProfileConcerns(
                none_known=dog.known_concerns_none,
                text=None if dog.known_concerns_none else dog.known_concerns,
            ),
            facts_by_situation=groups,
            not_observed=tuple(
                NotObserved(s, SITUATION_LABELS[s]) for s in coverage.not_observed
            ),
            contact=ProfileContact(dog.contact_url, dog.contact_email, dog.contact_phone),
            ask=ProfileAsk(
                enabled=True,
                max_question_chars=self._settings.qa_question_max_chars,
                limit_per_hour=self._settings.qa_limit_per_hour,
            ),
        )

    def _fact(self, f: PublicFact) -> ProfileFact:
        ranges = [Range(e.start_s, e.end_s, e.clip_id) for e in f.evidence]
        notice = (
            ProfileNotice(t.NOTICE_IN_PERSON_CODE, t.NOTICE_IN_PERSON_TEXT)
            if f.situation == "children_cats"
            else None
        )
        return ProfileFact(
            id=f.id,
            behavior=f.behavior,
            source=f.source,
            source_label=source_label(f.source),
            observed_on=f.observed_on,
            confirmed_by_label=confirmed_by_label(f.confirmed_role),
            clip_length=clip_length(f.source, ranges),
            notice=notice,
            evidence=tuple(
                ProfileEvidence(
                    clip_id=e.clip_id,
                    start_s=e.start_s,
                    end_s=e.end_s,
                    media_url=self._media.clip_media(e.clip_id),
                    captions_url=self._media.clip_captions(
                        e.clip_id, has_transcript=e.has_transcript
                    ),
                )
                for e in f.evidence
            ),
        )
