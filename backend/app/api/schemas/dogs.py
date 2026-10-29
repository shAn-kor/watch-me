"""Request and response models of the dog routes (01 sections 2 and 4)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator

from app.api.schemas.auth import iso_z, iso_z_required
from app.api.schemas.clips import ClipOut
from app.api.schemas.facts import ClipLengthOut, EvidenceOut, FlagOut
from app.api.schemas.vocab import (
    BlockedReason,
    DogStatus,
    FactOrigin,
    FactSource,
    FactStatus,
    RoleName,
    SessionFailCode,
    SessionStatus,
    Sex,
    SituationCode,
    Size,
)
from app.domain.coverage import Coverage
from app.services.coverage_service import ShortCoverage
from app.services.dog_service import (
    DogDetailView,
    DogListItem,
    DogView,
    SessionSummaryView,
)
from app.services.publish_service import ChecklistView, PublishResult
from app.services.views import FactView

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Age = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
Location = Annotated[str, StringConstraints(max_length=120)]


# ----------------------------------------------------------------- requests


class DogCreateIn(BaseModel):
    name: Name
    sex: Sex
    age_estimate: Age
    size: Size
    location: Location | None = None


class DogPatchIn(BaseModel):
    """Any subset; `location: null` clears. The other fields cannot be null."""

    name: Name | None = None
    sex: Sex | None = None
    age_estimate: Age | None = None
    size: Size | None = None
    location: Location | None = None

    @field_validator("name", "sex", "age_estimate", "size", mode="after")
    @classmethod
    def _not_null(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("must not be null")
        return value

    def patch(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)


class ChecklistIn(BaseModel):
    # Defaults to False so a hidden dog answers 404 before any body check (API-ORG-01).
    people_check: bool = False
    known_concerns: str | None = Field(default=None, max_length=4000)
    known_concerns_none: bool = False


# ---------------------------------------------------------------- responses


class DogOut(BaseModel):
    id: str
    name: str
    sex: Sex
    age_estimate: str
    size: Size
    location: str | None
    photo_url: str | None
    status: DogStatus
    public_slug: str | None
    public_path: str | None
    created_by: str
    created_at: str
    published_at: str | None
    adopted_at: str | None

    @classmethod
    def from_view(cls, v: DogView) -> DogOut:
        return cls(
            id=v.id,
            name=v.name,
            sex=v.sex,
            age_estimate=v.age_estimate,
            size=v.size,
            location=v.location,
            photo_url=v.photo_url,
            status=v.status,
            public_slug=v.public_slug,
            public_path=v.public_path,
            created_by=v.created_by,
            created_at=iso_z_required(v.created_at),
            published_at=iso_z(v.published_at),
            adopted_at=iso_z(v.adopted_at),
        )


class DogEnvelope(BaseModel):
    dog: DogOut


class ShortCoverageOut(BaseModel):
    situations_total: int
    situations_covered: int

    @classmethod
    def from_view(cls, v: ShortCoverage) -> ShortCoverageOut:
        return cls(situations_total=v.situations_total, situations_covered=v.situations_covered)


class CountsOut(BaseModel):
    draft_facts: int
    confirmed_facts: int
    sessions_in_review: int
    clips: int


class DogListItemOut(BaseModel):
    dog: DogOut
    coverage: ShortCoverageOut
    counts: CountsOut

    @classmethod
    def from_view(cls, v: DogListItem) -> DogListItemOut:
        return cls(
            dog=DogOut.from_view(v.dog),
            coverage=ShortCoverageOut.from_view(v.coverage),
            counts=CountsOut(
                draft_facts=v.counts.draft_facts,
                confirmed_facts=v.counts.confirmed_facts,
                sessions_in_review=v.counts.sessions_in_review,
                clips=v.counts.clips,
            ),
        )


class DogListOut(BaseModel):
    dogs: list[DogListItemOut]


class SituationCoverageOut(BaseModel):
    situation: SituationCode
    label: str
    covered: bool
    clip_count: int
    filmed_s: int
    confirmed_s: int


class NotObservedOut(BaseModel):
    situation: SituationCode
    label: str


class CoverageOut(BaseModel):
    situations_total: int
    situations_covered: int
    by_situation: list[SituationCoverageOut]
    not_observed: list[NotObservedOut]

    @classmethod
    def from_domain(cls, c: Coverage) -> CoverageOut:
        labels = {e.situation: e.label for e in c.entries}
        return cls(
            situations_total=c.situations_total,
            situations_covered=c.situations_covered,
            by_situation=[
                SituationCoverageOut(
                    situation=e.situation,
                    label=e.label,
                    covered=e.covered,
                    clip_count=e.clip_count,
                    filmed_s=e.filmed_s,
                    confirmed_s=e.confirmed_s,
                )
                for e in c.entries
            ],
            not_observed=[NotObservedOut(situation=s, label=labels[s]) for s in c.not_observed],
        )


class ChecklistOut(BaseModel):
    people_check: bool
    people_check_at: str | None
    known_concerns: str | None
    known_concerns_none: bool
    confirmed_fact_count: int
    ready_to_publish: bool
    missing: list[str]

    @classmethod
    def from_view(cls, v: ChecklistView) -> ChecklistOut:
        return cls(
            people_check=v.people_check,
            people_check_at=iso_z(v.people_check_at),
            known_concerns=v.known_concerns,
            known_concerns_none=v.known_concerns_none,
            confirmed_fact_count=v.confirmed_fact_count,
            ready_to_publish=v.ready_to_publish,
            missing=list(v.missing),
        )


class ChecklistEnvelope(BaseModel):
    checklist: ChecklistOut


class SessionOut(BaseModel):
    id: str
    dog_id: str
    member_id: str
    owner_name: str
    situations: list[SituationCode]
    observed_on: str
    status: SessionStatus
    fail_code: SessionFailCode | None
    created_at: str
    submitted_at: str | None
    review_ready_at: str | None
    clip_count: int
    ready_clip_count: int
    draft_fact_count: int

    @classmethod
    def from_view(cls, v: SessionSummaryView) -> SessionOut:
        return cls(
            id=v.id,
            dog_id=v.dog_id,
            member_id=v.member_id,
            owner_name=v.owner_name,
            situations=list(v.situations),
            observed_on=v.observed_on.isoformat(),
            status=v.status,
            fail_code=v.fail_code,
            created_at=iso_z_required(v.created_at),
            submitted_at=iso_z(v.submitted_at),
            review_ready_at=iso_z(v.review_ready_at),
            clip_count=v.clip_count,
            ready_clip_count=v.ready_clip_count,
            draft_fact_count=v.draft_fact_count,
        )


class ConfirmedOut(BaseModel):
    by_member_id: str
    by_name: str
    role: RoleName
    at: str


class FactOut(BaseModel):
    id: str
    dog_id: str
    session_id: str | None
    situation: SituationCode
    behavior: str
    source: FactSource
    origin: FactOrigin
    status: FactStatus
    flags: list[FlagOut]
    observed_on: str
    evidence: list[EvidenceOut]
    clip_length: ClipLengthOut
    confirmed: ConfirmedOut | None
    created_by: str | None
    can_confirm: bool
    blocked_reason: BlockedReason | None

    @classmethod
    def from_view(cls, v: FactView) -> FactOut:
        return cls(
            id=v.id,
            dog_id=v.dog_id,
            session_id=v.session_id,
            situation=v.situation,
            behavior=v.behavior,
            source=v.source,
            origin=v.origin,
            status=v.status,
            flags=[FlagOut.model_validate(f) for f in v.flags],
            observed_on=v.observed_on.isoformat(),
            evidence=[EvidenceOut.model_validate(e) for e in v.evidence],
            clip_length=ClipLengthOut.model_validate(v.clip_length),
            confirmed=(
                ConfirmedOut(
                    by_member_id=v.confirmed.by_member_id,
                    by_name=v.confirmed.by_name,
                    role=v.confirmed.role,
                    at=iso_z_required(v.confirmed.at),
                )
                if v.confirmed
                else None
            ),
            created_by=v.created_by,
            can_confirm=v.can_confirm,
            blocked_reason=v.blocked_reason,
        )


class DogDetailOut(BaseModel):
    dog: DogOut
    coverage: CoverageOut
    checklist: ChecklistOut
    sessions: list[SessionOut]
    clips: list[ClipOut]
    facts: list[FactOut]

    @classmethod
    def from_view(cls, v: DogDetailView) -> DogDetailOut:
        return cls(
            dog=DogOut.from_view(v.dog),
            coverage=CoverageOut.from_domain(v.coverage),
            checklist=ChecklistOut.from_view(v.checklist),
            sessions=[SessionOut.from_view(s) for s in v.sessions],
            clips=[ClipOut.from_view(c) for c in v.clips],
            facts=[FactOut.from_view(f) for f in v.facts],
        )


class PublishOut(BaseModel):
    dog: DogOut
    public_url: str

    @classmethod
    def from_result(cls, r: PublishResult) -> PublishOut:
        return cls(dog=DogOut.from_view(r.dog), public_url=r.public_url)


class DeleteOut(BaseModel):
    dog_id: str
    status: Literal["deleted"]
    purge: Literal["queued"]
