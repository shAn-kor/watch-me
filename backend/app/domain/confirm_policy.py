"""ConfirmPolicy: ordered confirm guards, pure (02 section 3.4 F5, 06 section 4.2).

`evaluate` returns the first failing error code or None. The same function
feeds `FactView.can_confirm`/`blocked_reason` and the confirm endpoint.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.domain.situations import STAFF_ONLY
from app.domain.wording import needs_acknowledgement

NOT_FOUND = "not_found"
CONSENT_REQUIRED = "consent_required"
INVALID_STATE = "invalid_state"
STAFF_ONLY_SITUATION = "staff_only_situation"
NOT_OWN_SESSION = "not_own_session"
FORBIDDEN_ROLE = "forbidden_role"
PLAYBACK_REQUIRED = "playback_required"
FLAGS_UNACKNOWLEDGED = "flags_unacknowledged"
PUBLISH_CHECKLIST_INCOMPLETE = "publish_checklist_incomplete"

_TOL = 1e-6


@dataclass(frozen=True)
class FactInfo:
    id: str
    org_id: str
    status: str
    merged: bool
    situation: str
    source: str
    session_id: str | None
    session_owner_id: str | None
    flags: Sequence[Mapping[str, Any]] = ()


@dataclass(frozen=True)
class EvidenceInfo:
    id: str
    start_s: float
    end_s: float


@dataclass(frozen=True)
class DogInfo:
    status: str
    people_check_at: Any | None = None


@dataclass(frozen=True)
class ActorInfo:
    id: str
    org_id: str
    role: str
    consent_accepted: bool


@dataclass(frozen=True)
class PlaybackSnapshot:
    evidence_id: str
    member_id: str
    start_s: float
    end_s: float


@dataclass(frozen=True)
class ConfirmContext:
    fact: FactInfo | None
    dog: DogInfo
    actor: ActorInfo
    evidence: Sequence[EvidenceInfo] = ()
    events: Sequence[PlaybackSnapshot] = ()
    acknowledge_flags: bool = False


def missing_playback_evidence_ids(ctx: ConfirmContext) -> tuple[str, ...]:
    """Evidence rows with no playback event of this actor matching the current range."""
    missing = []
    for row in ctx.evidence:
        played = any(
            e.evidence_id == row.id
            and e.member_id == ctx.actor.id
            and math.isclose(e.start_s, row.start_s, abs_tol=_TOL)
            and math.isclose(e.end_s, row.end_s, abs_tol=_TOL)
            for e in ctx.events
        )
        if not played:
            missing.append(row.id)
    return tuple(missing)


class ConfirmPolicy:
    def evaluate(self, ctx: ConfirmContext) -> str | None:
        fact, actor = ctx.fact, ctx.actor
        if fact is None or fact.org_id != actor.org_id:
            return NOT_FOUND
        if not actor.consent_accepted:
            return CONSENT_REQUIRED
        if fact.status != "draft" or not fact.merged:
            return INVALID_STATE
        if fact.situation in STAFF_ONLY and actor.role != "staff":
            return STAFF_ONLY_SITUATION
        if actor.role == "volunteer":
            if fact.session_id is None:
                return FORBIDDEN_ROLE
            if fact.session_owner_id != actor.id:
                return NOT_OWN_SESSION
        if missing_playback_evidence_ids(ctx):
            return PLAYBACK_REQUIRED
        if needs_acknowledgement(fact.flags) and not ctx.acknowledge_flags:
            return FLAGS_UNACKNOWLEDGED
        if ctx.dog.status == "published" and ctx.dog.people_check_at is None:
            return PUBLISH_CHECKLIST_INCOMPLETE
        return None
