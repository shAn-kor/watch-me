"""AI-layer types (04 sections 2 to 7). Frozen contract between pipeline/services and `ai`.

Adapters never see dog or session ids: the caller owns the ledger columns
`dog_id` and `session_id`. Every request carries `fixture_key`, used only by
the mock adapter.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.situations import SituationCode

# --------------------------------------------------------------------- usage


class Usage(BaseModel):
    """One provider round trip. The caller writes the ledger row (04 section 9.2)."""

    provider: str  # "muse", "mock", "local"
    model: str  # e.g. "muse-spark-1.3"
    tokens_in: int = 0
    tokens_out: int = 0
    audio_s: float = 0.0  # transcription only
    usd_micros: int = 0  # computed by the adapter (04 section 9.1)
    purpose: Literal["transcribe", "draft", "check", "qa_select", "spike"]


# ------------------------------------------------------------ 3. transcriber


class TranscribeRequest(BaseModel):
    audio_path: str  # 16 kHz mono 16-bit WAV from the transcode job
    duration_s: float  # clip duration, used to clamp segments
    lang_hint: Literal["en", "ko", "auto"] = "auto"
    keywords: list[str] = []  # dog name, shelter name; max 20 (verify provider limit)
    fixture_key: str | None = None  # mock adapter only


class TranscriptSegmentOut(BaseModel):
    seq: int  # 0-based, contiguous
    start_s: float  # one decimal, 0 <= start_s < end_s <= duration_s
    end_s: float
    text: str  # 1..500 chars, NFC, trimmed
    speaker: str | None = None  # provider label if any


class TranscriptResult(BaseModel):
    language: Literal["en", "ko", "other"]
    segments: list[TranscriptSegmentOut]  # may be empty
    full_text: str


# --------------------------------------------------------------- 4. drafter


class DraftFrame(BaseModel):
    t: int  # seconds, = i * k
    path: str  # frames/t{t}.jpg (the adapter base64-encodes)
    segment_ref: str | None = None  # segments mode only, e.g. "c1-seg2"


class DraftSegment(BaseModel):  # segments mode
    ref: str  # "c{clip_ord}-seg{n}", clip_ord = 1..3 in the session
    start_s: float
    end_s: float
    frame_ts: list[int]  # frames inside this segment


class DraftRequest(BaseModel):
    mode: Literal["frames", "segments"]
    clip_ord: int  # 1..3, only for labels
    duration_s: float
    k: int  # frame interval
    frames: list[DraftFrame]  # 1..48 items, ascending t
    segments: list[DraftSegment] = []  # segments mode only
    transcript: list[TranscriptSegmentOut]  # may be empty
    allowed_situations: list[SituationCode]  # session.situations, 1..8
    dog_name: str | None  # for the model to ignore; never repeated in output
    observed_on: date
    max_facts: int = 8
    fixture_key: str | None = None  # mock adapter only


class EvidenceFrames(BaseModel):
    start_t: int  # must be in frames[].t (enum in the schema)
    end_t: int  # >= start_t


class DraftFactOut(BaseModel):
    # Structural validation only; off-grid or reversed times are repaired later
    # by DraftIngestService (04 section 5). `extra="forbid"` = "extra fields".
    model_config = ConfigDict(extra="forbid")

    situation: SituationCode  # enum = allowed_situations
    behavior: str = Field(
        min_length=8, max_length=140
    )  # 02 allows 280; the prompt asks for 140
    source: Literal["clip", "narration"]
    # frames mode: 1..3 items {start_t, end_t}; segments mode: 1..3 refs "c1-seg2"
    evidence: list[EvidenceFrames] | list[str] = Field(min_length=1)


class DraftOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facts: list[DraftFactOut] = Field(max_length=8)  # 0..max_facts


# ---------------------------------------------------------------- 6. checker


class Flag(BaseModel):
    """Wording flag as stored in `fact.flags` and returned by the API."""

    code: Literal["banned_word", "trait_claim", "check_unavailable"]
    severity: Literal["warn", "info"]
    source: Literal["rules", "model", "system"]
    detail: str  # server-rendered, never model text


class CheckItem(BaseModel):
    ref: str  # "C1".. per call
    situation: SituationCode
    behavior: str  # the sentence under review
    source: Literal["clip", "narration", "staff_note"]


class CheckRequest(BaseModel):
    items: list[CheckItem] = Field(
        min_length=1, max_length=40
    )  # the batch for one session
    fixture_key: str | None = None  # mock adapter only


class CheckResult(BaseModel):
    ref: str
    kind: Literal[
        "trait_label",
        "judgment",
        "mental_state",
        "safety_claim",
        "paraphrased_trait",
        "none",
    ]
    phrase: str | None = None  # exact words from behavior; None when kind="none"


# --------------------------------------------------------------- 7. selector


class FactRef(BaseModel):
    ref: str  # "F1".."Fn", n <= 100, per request, profile order
    situation: SituationCode
    behavior: str  # fact.behavior exactly


class SelectRequest(BaseModel):
    question: str  # trimmed, NFC, 3..300 chars, untrusted
    facts: list[FactRef] = Field(min_length=1, max_length=100)
    max_refs: int = 5  # QA_MAX_FACTS
    fixture_key: str | None = None  # mock adapter only


class SelectOutput(BaseModel):
    refs: list[str]  # 0..max_refs, each in the request's alias set
