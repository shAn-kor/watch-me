"""`mock`: deterministic, offline, free adapter for all four protocols
(04 section 8.1, 07 sections 1.2 and 2.3).

Fixture file: `{fixtures_dir}/{fixture_key}.json`, falling back to
`default.json`. Faults are counted per fixture in process memory.

Fault errors: 04 8.1 says the mock converts to `JobError` exactly as a real
adapter; 07 (UT-AI-12) expects the raw `AiError` classes. Both are served:
the default converts, `raise_ai_errors=True` raises the `AiError` itself.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.ai.errors import (
    AiError,
    AiInvalidOutput,
    AiPermanentError,
    AiTransientError,
    Purpose,
    to_job_error,
)
from app.ai.types import (
    CheckRequest,
    CheckResult,
    DraftFactOut,
    DraftOutput,
    DraftRequest,
    SelectOutput,
    SelectRequest,
    TranscribeRequest,
    TranscriptResult,
    TranscriptSegmentOut,
    Usage,
)

_PURPOSE: dict[str, Purpose] = {
    "transcribe": "transcribe",
    "draft": "draft",
    "check": "check",
    "select": "qa_select",
}


class MockFixtureError(RuntimeError):
    """A test setup error: neither the fixture nor `default.json` exists, or it is malformed."""


class MockAdapter:
    def __init__(self, fixtures_dir: str | Path, *, raise_ai_errors: bool = False):
        self.fixtures_dir = Path(fixtures_dir)
        self.raise_ai_errors = raise_ai_errors
        self._calls: dict[tuple[str, str], int] = {}

    # ------------------------------------------------------------- fixtures
    def _load(self, key: str | None) -> tuple[str, dict[str, Any]]:
        names = [key, "default"] if key else ["default"]
        for name in names:
            path = self.fixtures_dir / f"{name}.json"
            if path.is_file():
                try:
                    return name, json.loads(path.read_text(encoding="utf-8"))
                except ValueError as exc:
                    raise MockFixtureError(f"fixture {path} is not valid JSON") from exc
        raise MockFixtureError(
            f"no mock fixture for key {key!r} and no default.json in {self.fixtures_dir}"
        )

    # --------------------------------------------------------------- faults
    def _fault(self, name: str, data: dict[str, Any], method: str) -> AiError | None:
        faults = data.get("faults")
        if not faults:
            return None
        if isinstance(faults, dict):  # 04 form: one spec per method
            spec = faults.get(method)
            counter = (name, method)
            entries = [spec] if spec else []
        else:  # 07 form: a list, played in order across all calls of the fixture
            entries = list(faults)
            counter = (name, "*")
        n = self._calls.get(counter, 0)
        self._calls[counter] = n + 1
        for spec in entries:
            times = int(spec.get("fail_times", 1))
            if n < times:
                return self._make_error(spec)
            n -= times
        return None

    @staticmethod
    def _make_error(spec: dict[str, Any]) -> AiError:
        kind = spec["kind"]
        if kind == "transient":
            return AiTransientError("mock transient fault", retry_after_s=spec.get("retry_after_s"))
        if kind == "permanent":
            return AiPermanentError("mock permanent fault")
        if kind == "invalid_output":
            # as if the adapter's own retry had failed too: two billed calls
            usages = [Usage(provider="mock", model="mock", purpose="draft")] * 2
            return AiInvalidOutput("mock invalid output", usages=list(usages))
        raise MockFixtureError(f"unknown fault kind {kind!r}")

    def _enter(self, key: str | None, method: str) -> dict[str, Any]:
        name, data = self._load(key)
        error = self._fault(name, data, method)
        if error is not None:
            purpose = _PURPOSE[method]
            error.usages = [u.model_copy(update={"purpose": purpose}) for u in error.usages]
            if self.raise_ai_errors:
                raise error
            raise to_job_error(error, purpose) from error
        return data

    @staticmethod
    def _usage(purpose: Purpose, req: Any, out: Any, audio_s: float = 0.0) -> list[Usage]:
        return [
            Usage(
                provider="mock",
                model="mock",
                tokens_in=len(req.model_dump_json()) // 4,
                tokens_out=len(out.model_dump_json()) // 4,
                audio_s=audio_s,
                usd_micros=0,
                purpose=purpose,
            )
        ]

    # ------------------------------------------------------------ protocols
    def transcribe(self, req: TranscribeRequest) -> tuple[TranscriptResult, list[Usage]]:
        data = self._enter(req.fixture_key, "transcribe")
        raw = data.get("transcript") or {}
        segments = [
            TranscriptSegmentOut(
                seq=i,
                start_s=s["start_s"],
                end_s=s["end_s"],
                text=s["text"],
                speaker=s.get("speaker"),
            )
            for i, s in enumerate(raw.get("segments", []))
        ]
        result = TranscriptResult(
            language=raw.get("language", "en"),
            segments=segments,
            full_text=" ".join(s.text for s in segments),
        )
        return result, self._usage("transcribe", req, result, audio_s=req.duration_s)

    def draft(self, req: DraftRequest) -> tuple[DraftOutput, list[Usage]]:
        data = self._enter(req.fixture_key, "draft")
        try:
            facts = [DraftFactOut.model_validate(f) for f in data.get("facts", [])]
        except ValueError as exc:
            raise MockFixtureError(f"fixture facts are not valid: {exc}") from exc
        kept = [f for f in facts if f.situation in req.allowed_situations]
        out = DraftOutput(facts=kept[: req.max_facts])
        return out, self._usage("draft", req, out)

    def check(self, req: CheckRequest) -> tuple[list[CheckResult], list[Usage]]:
        data = self._enter(req.fixture_key, "check")
        rules = data.get("check", [])
        results: list[CheckResult] = []
        for item in req.items:
            text = item.behavior.lower()
            hit = next((r for r in rules if r["match"].lower() in text), None)
            if hit is None:
                results.append(CheckResult(ref=item.ref, kind="none", phrase=None))
            else:
                results.append(
                    CheckResult(ref=item.ref, kind=hit["kind"], phrase=hit.get("phrase", hit["match"]))
                )
        usages = self._usage("check", req, SelectOutput(refs=[r.ref for r in results]))
        return results, usages

    def select(self, req: SelectRequest) -> tuple[SelectOutput, list[Usage]]:
        data = self._enter(req.fixture_key, "select")
        question = req.question.lower()
        refs: list[str] = []
        for rule in data.get("select", []):
            needles = rule.get("question_contains") or [""]  # none given: always matches
            if any(n.lower() in question for n in needles):
                refs = list(rule["refs"])  # returned as is, even outside the request's set
                break
        out = SelectOutput(refs=refs)
        return out, self._usage("qa_select", req, out)
