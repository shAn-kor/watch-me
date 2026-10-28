"""Scripted AI fakes for the test container (07 section 1.2).

These are Phase 0 stand-ins. Lane C ships the real `MockAdapter` (fixture
files, `faults`); tests that need it build the container with that instead.
Each fake records its calls (`CallCounter`-style) and plays a script: a queue of
results or exceptions, then a default.
"""

from __future__ import annotations

from collections import deque
from typing import Any

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


class _Scripted:
    purpose: str = "draft"

    def __init__(self, *script: Any, default: Any = None):
        self._script: deque[Any] = deque(script)
        self._default = default
        self.calls: list[Any] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def push(self, *items: Any) -> None:
        self._script.extend(items)

    def _next(self, req: Any) -> Any:
        self.calls.append(req)
        item = self._script.popleft() if self._script else self._default
        if isinstance(item, BaseException):
            raise item
        return item

    def _usage(self) -> list[Usage]:
        return [Usage(provider="mock", model="mock", purpose=self.purpose)]  # type: ignore[arg-type]


class ScriptedTranscriber(_Scripted):
    purpose = "transcribe"

    def __init__(self, *script: Any):
        super().__init__(
            *script, default=TranscriptResult(language="en", segments=[], full_text="")
        )

    def transcribe(
        self, req: TranscribeRequest
    ) -> tuple[TranscriptResult, list[Usage]]:
        return self._next(req), self._usage()


class ScriptedDrafter(_Scripted):
    purpose = "draft"

    def __init__(self, *script: Any):
        super().__init__(*script, default=DraftOutput(facts=[]))

    def draft(self, req: DraftRequest) -> tuple[DraftOutput, list[Usage]]:
        return self._next(req), self._usage()


class ScriptedChecker(_Scripted):
    purpose = "check"

    def __init__(self, *script: Any):
        super().__init__(*script, default=[])

    def check(self, req: CheckRequest) -> tuple[list[CheckResult], list[Usage]]:
        return self._next(req), self._usage()


class ScriptedSelector(_Scripted):
    purpose = "qa_select"

    def __init__(self, *script: Any):
        super().__init__(*script, default=SelectOutput(refs=[]))

    def select(self, req: SelectRequest) -> tuple[SelectOutput, list[Usage]]:
        return self._next(req), self._usage()


def scripted_ai_slots():
    """An `AiSlots` whose four roles are scripted fakes (empty scripts)."""
    from app.container import AiSlots

    return AiSlots(
        transcriber=ScriptedTranscriber(),
        drafter=ScriptedDrafter(),
        checker=ScriptedChecker(),
        selector=ScriptedSelector(),
    )
