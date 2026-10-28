"""Provider interfaces (04 section 2). All methods are synchronous.

Each call takes one request object and returns `(result, list[Usage])`: one
`Usage` per provider call (two when the adapter retried invalid output). The
caller writes the ledger. On failure an adapter raises `app.errors.JobError`
carrying the `Usage` rows of the calls already made.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.ai.types import (
    CheckRequest,
    CheckResult,
    DraftOutput,
    DraftRequest,
    SelectOutput,
    SelectRequest,
    TranscribeRequest,
    TranscriptResult,
    Usage,
)


@runtime_checkable
class Transcriber(Protocol):
    def transcribe(
        self, req: TranscribeRequest
    ) -> tuple[TranscriptResult, list[Usage]]: ...


@runtime_checkable
class FactDrafter(Protocol):
    def draft(self, req: DraftRequest) -> tuple[DraftOutput, list[Usage]]: ...


@runtime_checkable
class WordingChecker(Protocol):
    def check(self, req: CheckRequest) -> tuple[list[CheckResult], list[Usage]]: ...


@runtime_checkable
class FactSelector(Protocol):
    def select(self, req: SelectRequest) -> tuple[SelectOutput, list[Usage]]: ...
