"""EvidenceValidator (06 section 3.2; 02 I-3, I-4; 01 evidence rules).

Validates the evidence list of a hand-added or edited fact. Lane P's draft ingest
repairs model output with `domain.ranges` instead; this class is for member input.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from app.errors import ClipNotReady, EvidenceOutOfRange, NotFound, NotOwnSession
from app.repositories.facts import FactRepository
from app.services.views import Principal

MIN_LEN_S = 1.0
MAX_LEN_S = 60.0
_EPS = 1e-6


@dataclass(frozen=True)
class EvidenceInput:
    clip_id: str
    start_s: float
    end_s: float
    id: str | None = None


@dataclass(frozen=True)
class ValidEvidence:
    """A checked item with the 0.1 s rounding applied and its clip's session."""

    clip_id: str
    start_s: float
    end_s: float
    session_id: str
    session_observed_on: date
    id: str | None = None


def range_problem(start_s: float, end_s: float, duration_s: float) -> str | None:
    """`start_negative`, `too_short`, `too_long`, `past_clip_end`, or None when the
    range is valid. Values are rounded to 0.1 s first."""
    start, end = round(start_s, 1), round(end_s, 1)
    if start < 0:
        return "start_negative"
    length = round(end - start, 6)
    if length < MIN_LEN_S - _EPS:
        return "too_short"
    if length > MAX_LEN_S + _EPS:
        return "too_long"
    if end > duration_s + _EPS:
        return "past_clip_end"
    return None


class EvidenceValidator:
    def validate(
        self,
        repo: FactRepository,
        principal: Principal,
        dog_id: str,
        items: Sequence[EvidenceInput],
    ) -> list[ValidEvidence]:
        """Check each item in order and stop at the first failure:
        unknown clip or other org `not_found`; clip of another dog
        `evidence_out_of_range`; volunteer outside own session `not_own_session`;
        clip not ready `clip_not_ready`; bad range `evidence_out_of_range`."""
        out: list[ValidEvidence] = []
        for item in items:
            ctx = repo.get_clip_context(item.clip_id)
            if ctx is None or ctx.org_id != principal.org_id or ctx.clip.deleted_at is not None:
                raise NotFound()
            clip = ctx.clip
            if clip.dog_id != dog_id:
                raise EvidenceOutOfRange(
                    "The clip belongs to another dog.", details={"clip_id": clip.id}
                )
            if not principal.is_staff and ctx.session_owner_id != principal.member_id:
                raise NotOwnSession()
            if not clip.is_ready:
                raise ClipNotReady(details={"clip_id": clip.id})
            problem = range_problem(item.start_s, item.end_s, clip.duration_s)
            if problem is not None:
                raise EvidenceOutOfRange(
                    details={"clip_id": clip.id, "problem": problem, "duration_s": clip.duration_s}
                )
            out.append(
                ValidEvidence(
                    clip_id=clip.id,
                    start_s=round(item.start_s, 1),
                    end_s=round(item.end_s, 1),
                    session_id=clip.session_id,
                    session_observed_on=ctx.session_observed_on,
                    id=item.id,
                )
            )
        return out
