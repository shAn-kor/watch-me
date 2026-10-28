"""Closed vocabularies of the data model (02 sections 2 and 3).

Pure stdlib. Models build their CHECK constraints from these, so the database
and the code cannot disagree. All members are `str` so they compare and
serialize as the plain snake_case values of the API.
"""

from __future__ import annotations

from enum import StrEnum


class Situation(StrEnum):
    """The 8 situation codes, in PRD 5.2 order (02 section 0)."""

    NEW_PERSON = "new_person"
    HANDLING = "handling"
    LEASH_WALK = "leash_walk"
    OTHER_DOG = "other_dog"
    FOOD_TOYS = "food_toys"
    ALONE_TIME = "alone_time"
    INDOORS_REST = "indoors_rest"
    CHILDREN_CATS = "children_cats"


class DogStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ADOPTED = "adopted"
    DELETED = "deleted"


class Sex(StrEnum):
    MALE = "male"
    FEMALE = "female"
    UNKNOWN = "unknown"


class Size(StrEnum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class Role(StrEnum):
    STAFF = "staff"
    VOLUNTEER = "volunteer"


class SessionStatus(StrEnum):
    OPEN = "open"
    PROCESSING = "processing"
    REVIEW = "review"
    FAILED = "failed"


class ClipStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class ClipStep(StrEnum):
    TRANSCODE = "transcode"
    TRANSCRIBE = "transcribe"
    SAMPLE = "sample"
    DRAFT = "draft"


class FactStatus(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    DELETED = "deleted"


class Origin(StrEnum):
    AI_UNCHANGED = "ai_unchanged"
    HUMAN_EDITED = "human_edited"
    HUMAN_ADDED = "human_added"


class Source(StrEnum):
    CLIP = "clip"
    NARRATION = "narration"
    STAFF_NOTE = "staff_note"


class JobType(StrEnum):
    TRANSCODE = "transcode"
    TRANSCRIBE = "transcribe"
    SAMPLE = "sample"
    DRAFT = "draft"
    MERGE = "merge"
    CHECK = "check"
    PURGE_CLIP = "purge_clip"
    PURGE_DOG = "purge_dog"
    RETENTION_SWEEP = "retention_sweep"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FailCode(StrEnum):
    """Clip fail codes (02 section 3.3), session fail codes (02 section 2.4),
    and the purge job code used by `JobError` (06 section 3.4)."""

    # clip.fail_code
    UNSUPPORTED_FILE = "unsupported_file"
    TOO_LONG = "too_long"
    TRANSCODE_FAILED = "transcode_failed"
    AI_FAILED = "ai_failed"
    AI_INVALID_OUTPUT = "ai_invalid_output"
    # session.fail_code
    NO_USABLE_CLIP = "no_usable_clip"
    MERGE_FAILED = "merge_failed"
    # job-only
    PURGE_FAILED = "purge_failed"


CLIP_FAIL_CODES: tuple[FailCode, ...] = (
    FailCode.UNSUPPORTED_FILE,
    FailCode.TOO_LONG,
    FailCode.TRANSCODE_FAILED,
    FailCode.AI_FAILED,
    FailCode.AI_INVALID_OUTPUT,
)
SESSION_FAIL_CODES: tuple[FailCode, ...] = (
    FailCode.NO_USABLE_CLIP,
    FailCode.MERGE_FAILED,
)
# Clip fail codes a user may retry by hand (02 section 3.3, C6).
MANUALLY_RETRYABLE_CLIP_CODES: frozenset[FailCode] = frozenset(
    {FailCode.TRANSCODE_FAILED, FailCode.AI_FAILED, FailCode.AI_INVALID_OUTPUT}
)


class QaOutcome(StrEnum):
    ANSWERED = "answered"
    NOT_OBSERVED = "not_observed"
    HEALTH_REDIRECT = "health_redirect"
    ERROR = "error"


class CostPurpose(StrEnum):
    TRANSCRIBE = "transcribe"
    DRAFT = "draft"
    CHECK = "check"
    QA_SELECT = "qa_select"
    SPIKE = "spike"


class FlagCode(StrEnum):
    BANNED_WORD = "banned_word"
    TRAIT_CLAIM = "trait_claim"
    CHECK_UNAVAILABLE = "check_unavailable"


class FlagSeverity(StrEnum):
    WARN = "warn"
    INFO = "info"


class FlagSource(StrEnum):
    RULES = "rules"
    MODEL = "model"
    SYSTEM = "system"


def values(enum_cls: type[StrEnum]) -> tuple[str, ...]:
    """Plain string values of an enum, for CHECK constraints."""
    return tuple(member.value for member in enum_cls)
