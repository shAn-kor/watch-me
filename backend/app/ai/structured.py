"""`StructuredCaller`: validate a model's JSON, retry once, collect `Usage`
(04 section 8.2, 06 section 3.3, D2).

It does nothing else. Transport and HTTP errors are raised by `send` as
`AiTransientError` / `AiPermanentError` and are not retried here.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from app.ai.cost import PriceTable
from app.ai.errors import AiError, AiInvalidOutput, Purpose
from app.ai.types import Usage

T = TypeVar("T", bound=BaseModel)
Message = dict[str, Any]


@dataclass
class RawCompletion:
    """What the chat boundary hands back, whatever the SDK looks like."""

    content: str | None
    finish_reason: str | None = "stop"
    refusal: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0


@dataclass
class StructuredResult(Generic[T]):
    value: T
    usages: list[Usage] = field(default_factory=list)


def error_summary(error: ValidationError | ValueError, limit: int = 5) -> str:
    """`loc`, `type` and `msg` of at most `limit` errors. Never echoes input values."""
    if isinstance(error, ValidationError):
        parts = [
            f"{'.'.join(str(x) for x in e['loc']) or '(root)'}: {e['type']}: {e['msg']}"
            for e in error.errors(include_input=False, include_url=False)[:limit]
        ]
        return "; ".join(parts)
    return "the answer is not valid JSON"


class StructuredCaller:
    def __init__(self, prices: PriceTable, *, provider: str, model: str):
        self._prices = prices
        self._provider = provider
        self._model = model

    def _usage(self, raw: RawCompletion, purpose: Purpose) -> Usage:
        return Usage(
            provider=self._provider,
            model=self._model,
            tokens_in=raw.tokens_in,
            tokens_out=raw.tokens_out,
            usd_micros=self._prices.usd_micros(
                self._provider, self._model, raw.tokens_in, raw.tokens_out
            ),
            purpose=purpose,
        )

    @staticmethod
    def _parse(raw: RawCompletion, schema: type[T]) -> T:
        """Raises `ValidationError` or `ValueError` when the completion is invalid."""
        if raw.refusal:
            raise ValueError("the model refused")
        if raw.finish_reason not in (None, "stop"):
            raise ValueError(f"finish_reason={raw.finish_reason}")
        if not raw.content:
            raise ValueError("empty content")
        try:
            data = json.loads(raw.content)
        except ValueError as exc:
            raise ValueError("not JSON") from exc
        return schema.model_validate(data)

    def call(
        self,
        send: Callable[[list[Message]], RawCompletion],
        messages: Sequence[Message],
        schema: type[T],
        purpose: Purpose,
    ) -> StructuredResult[T]:
        usages: list[Usage] = []
        msgs = list(messages)
        for attempt in (1, 2):
            try:
                raw = send(msgs)
            except AiError as exc:
                exc.usages = usages + exc.usages  # earlier billed calls still reach the ledger
                raise
            usages.append(self._usage(raw, purpose))
            try:
                return StructuredResult(self._parse(raw, schema), usages)
            except (ValidationError, ValueError) as exc:
                if attempt == 2:
                    raise AiInvalidOutput(
                        f"invalid output twice: {error_summary(exc)}", usages=usages
                    ) from exc
                msgs = msgs + [
                    {"role": "assistant", "content": raw.content or ""},
                    {
                        "role": "user",
                        "content": (
                            f"Your last answer was not valid: {error_summary(exc)}. "
                            "Answer again with JSON that matches the schema."
                        ),
                    },
                ]
        raise AssertionError("unreachable")  # pragma: no cover
