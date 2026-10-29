"""Closed vocabularies of the responses as `Literal` types (01 section 2, 02 sections 2 and 3).

OpenAPI lists these values, so the frontend contract check (FE-API-05) sees them.
`tests/unit/test_schema_vocab.py` checks each alias against `app.domain.enums`.
"""

from __future__ import annotations

from typing import Literal

from app.domain.situations import SituationCode

__all__ = [
    "AskOutcome",
    "BlockedReason",
    "ClipFailCode",
    "ClipStatus",
    "ClipStep",
    "DogStatus",
    "FactOrigin",
    "FactSource",
    "FactStatus",
    "FlagCode",
    "FlagSeverity",
    "FlagSource",
    "RoleName",
    "SessionFailCode",
    "SessionStatus",
    "Sex",
    "SituationCode",
    "Size",
]

Sex = Literal["male", "female", "unknown"]
Size = Literal["small", "medium", "large"]
RoleName = Literal["staff", "volunteer"]
DogStatus = Literal["draft", "published", "adopted", "deleted"]
SessionStatus = Literal["open", "processing", "review", "failed"]
SessionFailCode = Literal["no_usable_clip", "merge_failed"]
ClipStatus = Literal["uploaded", "processing", "ready", "failed"]
ClipStep = Literal["transcode", "transcribe", "sample", "draft"]
ClipFailCode = Literal[
    "unsupported_file", "too_long", "transcode_failed", "ai_failed", "ai_invalid_output"
]
# `deleted` facts are never returned (01 section 2).
FactStatus = Literal["draft", "confirmed"]
FactOrigin = Literal["ai_unchanged", "human_edited", "human_added"]
FactSource = Literal["clip", "narration", "staff_note"]
FlagCode = Literal["banned_word", "trait_claim", "check_unavailable"]
FlagSeverity = Literal["warn", "info"]
FlagSource = Literal["rules", "model", "system"]
# `error` is never returned: the two 503s are error responses (01 section 6.2).
AskOutcome = Literal["answered", "not_observed", "health_redirect"]
# First failing confirm guard (02 section 3.4); `confirm_policy` holds the same constants.
BlockedReason = Literal[
    "not_found",
    "consent_required",
    "invalid_state",
    "staff_only_situation",
    "not_own_session",
    "forbidden_role",
    "playback_required",
    "flags_unacknowledged",
    "publish_checklist_incomplete",
]
