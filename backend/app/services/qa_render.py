"""Answer rendering (03 section 7, I-16). `text` is `fact.behavior` and nothing else."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date

from app.domain.labels import ClipLength, clip_length, confirmed_by_label, source_label
from app.domain.ranges import Range
from app.domain.situations import SITUATION_LABELS
from app.repositories.public_facts import PublicFact
from app.services import qa_templates as t
from app.services.views import MediaUrls


@dataclass(frozen=True, slots=True)
class QaEvidence:
    clip_id: str
    start_s: float
    end_s: float
    media_url: str
    captions_url: str | None


@dataclass(frozen=True, slots=True)
class QaNotice:
    code: str
    text: str


@dataclass(frozen=True, slots=True)
class QaLine:
    fact_id: str
    text: str
    situation: str
    situation_label: str
    source_label: str
    observed_on: date
    confirmed_by_label: str
    clip_length: ClipLength
    notice: QaNotice | None
    evidence: tuple[QaEvidence, ...]


@dataclass(frozen=True, slots=True)
class QaContact:
    url: str | None
    email: str | None
    phone: str | None


@dataclass(frozen=True, slots=True)
class QaAnswer:
    outcome: str
    heading: str
    hint: str | None
    lines: tuple[QaLine, ...]
    cited_fact_ids: tuple[str, ...]
    contact: QaContact | None = None
    remaining_this_hour: int = 0

    def with_remaining(self, remaining: int) -> QaAnswer:
        return replace(self, remaining_this_hour=remaining)


class AnswerRenderer:
    def __init__(self, media_urls: MediaUrls) -> None:
        self._media = media_urls

    def answered(self, facts: Sequence[PublicFact]) -> QaAnswer:
        lines = tuple(self._line(f) for f in facts)
        return QaAnswer(
            outcome="answered",
            heading=t.HEADING_ANSWERED,
            hint=None,
            lines=lines,
            cited_fact_ids=tuple(ln.fact_id for ln in lines),
        )

    def not_observed(self) -> QaAnswer:
        return QaAnswer(
            outcome="not_observed",
            heading=t.HEADING_NOT_OBSERVED,
            hint=t.HINT_NOT_OBSERVED,
            lines=(),
            cited_fact_ids=(),
        )

    def health_redirect(self, contact: QaContact) -> QaAnswer:
        return QaAnswer(
            outcome="health_redirect",
            heading=t.HEADING_HEALTH,
            hint=t.HINT_HEALTH,
            lines=(),
            cited_fact_ids=(),
            contact=contact,
        )

    def _line(self, f: PublicFact) -> QaLine:
        ranges = [Range(e.start_s, e.end_s, e.clip_id) for e in f.evidence]
        notice = (
            QaNotice(t.NOTICE_IN_PERSON_CODE, t.NOTICE_IN_PERSON_TEXT)
            if f.situation == "children_cats"
            else None
        )
        return QaLine(
            fact_id=f.id,
            text=f.behavior,
            situation=f.situation,
            situation_label=SITUATION_LABELS[f.situation],
            source_label=source_label(f.source),
            observed_on=f.observed_on,
            confirmed_by_label=confirmed_by_label(f.confirmed_role),
            clip_length=clip_length(f.source, ranges),
            notice=notice,
            evidence=tuple(
                QaEvidence(
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
