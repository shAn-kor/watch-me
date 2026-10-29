"""Public Q&A schemas (01 section 6.2). Lane S5 adds the profile schemas here."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.api.schemas.vocab import AskOutcome, FactSource, Sex, SituationCode, Size
from app.services.public_profile_service import PublicProfile
from app.services.qa_render import QaAnswer, QaLine


class AskIn(BaseModel):
    question: str


class ClipLengthOut(BaseModel):
    clip_count: int
    seconds: int
    label: str


class NoticeOut(BaseModel):
    code: str
    text: str


class EvidenceOut(BaseModel):
    clip_id: str
    start_s: float
    end_s: float
    media_url: str
    captions_url: str | None


class AnswerLineOut(BaseModel):
    fact_id: str
    text: str
    situation: SituationCode
    situation_label: str
    source_label: str
    observed_on: date
    confirmed_by_label: str
    clip_length: ClipLengthOut
    notice: NoticeOut | None
    evidence: list[EvidenceOut]

    @classmethod
    def from_line(cls, ln: QaLine) -> AnswerLineOut:
        return cls(
            fact_id=ln.fact_id,
            text=ln.text,
            situation=ln.situation,
            situation_label=ln.situation_label,
            source_label=ln.source_label,
            observed_on=ln.observed_on,
            confirmed_by_label=ln.confirmed_by_label,
            clip_length=ClipLengthOut(
                clip_count=ln.clip_length.clip_count,
                seconds=ln.clip_length.seconds,
                label=ln.clip_length.label,
            ),
            notice=NoticeOut(code=ln.notice.code, text=ln.notice.text) if ln.notice else None,
            evidence=[
                EvidenceOut(
                    clip_id=e.clip_id,
                    start_s=e.start_s,
                    end_s=e.end_s,
                    media_url=e.media_url,
                    captions_url=e.captions_url,
                )
                for e in ln.evidence
            ],
        )


class ContactOut(BaseModel):
    url: str | None
    email: str | None
    phone: str | None


class LimitsOut(BaseModel):
    remaining_this_hour: int


class AskOut(BaseModel):
    """`hint` and `contact` exist only for the outcomes that define them, so the
    router dumps with `exclude_unset=True`."""

    model_config = ConfigDict(extra="forbid")

    outcome: AskOutcome
    heading: str
    hint: str | None = None
    lines: list[AnswerLineOut]
    cited_fact_ids: list[str]
    contact: ContactOut | None = None
    limits: LimitsOut

    @classmethod
    def from_answer(cls, a: QaAnswer) -> AskOut:
        fields: dict[str, object] = {
            "outcome": a.outcome,
            "heading": a.heading,
            "lines": [AnswerLineOut.from_line(ln) for ln in a.lines],
            "cited_fact_ids": list(a.cited_fact_ids),
            "limits": LimitsOut(remaining_this_hour=a.remaining_this_hour),
        }
        if a.outcome in ("not_observed", "health_redirect"):
            fields["hint"] = a.hint
        if a.contact is not None:
            fields["contact"] = ContactOut(
                url=a.contact.url, email=a.contact.email, phone=a.contact.phone
            )
        return cls(**fields)  # type: ignore[arg-type]


# ------------------------------------------------------------ profile (lane S5)


class ProfileDogOut(BaseModel):
    slug: str
    name: str
    sex: Sex
    age_estimate: str
    size: Size
    location: str
    photo_url: str | None
    published_at: datetime


class ProfileOrgOut(BaseModel):
    name: str
    country: str


class SituationCoverageOut(BaseModel):
    situation: SituationCode
    label: str
    covered: bool
    clip_count: int
    filmed_s: int
    confirmed_s: int


class ProfileCoverageOut(BaseModel):
    situations_total: int
    situations_covered: int
    summary: str
    by_situation: list[SituationCoverageOut]


class KnownConcernsOut(BaseModel):
    none_known: bool
    text: str | None


class ProfileFactOut(BaseModel):
    id: str
    behavior: str
    source: FactSource
    source_label: str
    observed_on: date
    confirmed_by_label: str
    clip_length: ClipLengthOut
    notice: NoticeOut | None
    evidence: list[EvidenceOut]


class FactGroupOut(BaseModel):
    situation: SituationCode
    label: str
    facts: list[ProfileFactOut]


class NotObservedOut(BaseModel):
    situation: SituationCode
    label: str


class AskInfoOut(BaseModel):
    enabled: bool
    max_question_chars: int
    limit_per_hour: int


class ProfileOut(BaseModel):
    banner_id: str
    dog: ProfileDogOut
    org: ProfileOrgOut
    coverage: ProfileCoverageOut
    known_concerns: KnownConcernsOut
    facts_by_situation: list[FactGroupOut]
    not_observed: list[NotObservedOut]
    contact: ContactOut
    ask: AskInfoOut

    @classmethod
    def from_profile(cls, p: PublicProfile) -> ProfileOut:
        return cls.model_validate(
            {
                "banner_id": p.banner_id,
                "dog": p.dog,
                "org": {"name": p.org_name, "country": p.org_country},
                "coverage": {
                    "situations_total": p.coverage.situations_total,
                    "situations_covered": p.coverage.situations_covered,
                    "summary": p.coverage.summary,
                    "by_situation": p.coverage.by_situation,
                },
                "known_concerns": p.known_concerns,
                "facts_by_situation": p.facts_by_situation,
                "not_observed": p.not_observed,
                "contact": p.contact,
                "ask": p.ask,
            },
            from_attributes=True,
        )
