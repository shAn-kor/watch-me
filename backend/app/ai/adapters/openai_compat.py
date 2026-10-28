"""`openai_compat`: FactDrafter, WordingChecker and FactSelector over one chat
boundary (04 section 8.2, 06 section 3.3).

`ChatClient` is the only code that touches the `openai` SDK. It turns SDK
errors into `AiTransientError` / `AiPermanentError` (04 section 8.7) and hands
back a `RawCompletion`. The SDK runs with `max_retries=0`: the one schema retry
lives in `StructuredCaller`, job retries in the worker.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

import openai
from pydantic import BaseModel, ConfigDict

from app.ai.cost import PriceTable
from app.ai.errors import (
    AiError,
    AiPermanentError,
    AiTransientError,
    Purpose,
    to_job_error,
)
from app.ai.prompts.check import build_check_messages, check_response_format
from app.ai.prompts.draft import (
    _default_read_image,
    build_draft_messages,
    draft_response_format,
)
from app.ai.prompts.select import build_select_messages, select_response_format
from app.ai.structured import RawCompletion, StructuredCaller
from app.ai.types import (
    CheckRequest,
    CheckResult,
    DraftOutput,
    DraftRequest,
    SelectOutput,
    SelectRequest,
    Usage,
)
from app.config import AiConnection

PROVIDER = "muse"
# 04 section 8.2 asks for the lowest effort. The accepted values are "(verify)"
# (D11), and a wrong value is a 400 that fails every call, so it is off until the
# day-1 spike names one.
REASONING_EFFORT: str | None = None
MAX_TOKENS = {"draft": 1500, "check": 600, "qa_select": 100}
TEMPERATURE = {"draft": 0.2, "check": 0.0, "qa_select": 0.0}


def _retry_after(headers: Any) -> float | None:
    """Seconds from `Retry-After`. The HTTP-date form is not used (a hint only)."""
    try:
        return max(0.0, float(headers.get("retry-after")))
    except (AttributeError, TypeError, ValueError):
        return None


class ChatClient:
    def __init__(self, sdk: Any, model: str, *, stream: bool = False):
        self._sdk = sdk
        self.model = model
        self._stream = stream

    def complete(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any],
        *,
        temperature: float,
        max_tokens: int,
        stream: bool | None = None,
    ) -> RawCompletion:
        kwargs: dict[str, Any] = dict(
            model=self.model,
            messages=messages,
            response_format=response_format,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if REASONING_EFFORT:
            kwargs["reasoning_effort"] = REASONING_EFFORT
        use_stream = self._stream if stream is None else stream
        try:
            if use_stream:
                return self._read_stream(kwargs)
            return self._raw(self._sdk.chat.completions.create(**kwargs))
        except openai.APIStatusError as exc:
            raise self._status_error(exc) from None
        except openai.APIConnectionError as exc:  # includes APITimeoutError
            raise AiTransientError(f"network error: {type(exc).__name__}") from None

    @staticmethod
    def _status_error(exc: openai.APIStatusError) -> AiError:
        # Only the status and the provider code are kept; the body never is.
        code = exc.code if isinstance(getattr(exc, "code", None), str) else None
        detail = f"HTTP {exc.status_code}" + (f" {code}" if code else "")
        if exc.status_code in (408, 429) or exc.status_code >= 500:
            return AiTransientError(
                detail, retry_after_s=_retry_after(exc.response.headers)
            )
        return AiPermanentError(detail)

    @staticmethod
    def _raw(resp: Any) -> RawCompletion:
        usage = getattr(resp, "usage", None)
        tokens_in = int(getattr(usage, "prompt_tokens", 0) or 0)
        tokens_out = int(getattr(usage, "completion_tokens", 0) or 0)
        if not resp.choices:
            return RawCompletion(None, None, None, tokens_in, tokens_out)
        choice = resp.choices[0]
        msg = choice.message
        return RawCompletion(
            content=msg.content,
            finish_reason=choice.finish_reason,
            refusal=getattr(msg, "refusal", None),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

    def _read_stream(self, kwargs: dict[str, Any]) -> RawCompletion:
        """Streamed read (AI_STREAM=true) for HTTP 504 on long drafts."""
        content: list[str] = []
        finish: str | None = None
        refusal: list[str] = []
        tokens_in = tokens_out = 0
        for chunk in self._sdk.chat.completions.create(
            stream=True, stream_options={"include_usage": True}, **kwargs
        ):
            if getattr(chunk, "usage", None):
                tokens_in = int(chunk.usage.prompt_tokens or 0)
                tokens_out = int(chunk.usage.completion_tokens or 0)
            for choice in chunk.choices or []:
                delta = choice.delta
                if getattr(delta, "content", None):
                    content.append(delta.content)
                if getattr(delta, "refusal", None):
                    refusal.append(delta.refusal)
                if choice.finish_reason:
                    finish = choice.finish_reason
        return RawCompletion("".join(content) or None, finish, "".join(refusal) or None, tokens_in, tokens_out)


def build_chat_client(conn: AiConnection, *, timeout_s: float, stream: bool = False) -> ChatClient:
    sdk = openai.OpenAI(
        base_url=conn.base_url, api_key=conn.api_key, timeout=timeout_s, max_retries=0
    )
    return ChatClient(sdk, conn.model, stream=stream)


class _Base:
    purpose: Purpose

    def __init__(self, chat: ChatClient, prices: PriceTable, *, strict: bool = True):
        self._chat = chat
        self._strict = strict
        self._caller = StructuredCaller(prices, provider=PROVIDER, model=chat.model)

    def _call(
        self,
        messages: list[dict[str, Any]],
        fmt: dict[str, Any],
        schema: type[BaseModel],
        *,
        stream: bool | None = None,
    ):
        key = self.purpose
        return self._caller.call(
            lambda msgs: self._chat.complete(
                msgs, fmt, temperature=TEMPERATURE[key], max_tokens=MAX_TOKENS[key], stream=stream
            ),
            messages,
            schema,
            self.purpose,
        )


class OpenAICompatDrafter(_Base):
    purpose: Purpose = "draft"

    def __init__(
        self,
        chat: ChatClient,
        prices: PriceTable,
        *,
        strict: bool = True,
        stream: bool | None = None,
        read_image: Callable[[str], bytes] = _default_read_image,
    ):
        super().__init__(chat, prices, strict=strict)
        self._stream = stream
        self._read_image = read_image

    def draft(self, req: DraftRequest) -> tuple[DraftOutput, list[Usage]]:
        try:
            res = self._call(
                build_draft_messages(req, read_image=self._read_image),
                draft_response_format(req, strict=self._strict),
                DraftOutput,
                stream=self._stream,
            )
        except AiError as exc:
            raise to_job_error(exc, "draft") from exc
        return res.value, res.usages


class _CheckRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str
    kind: Literal[
        "trait_label", "judgment", "mental_state", "safety_claim", "paraphrased_trait", "none"
    ]
    phrase: str = ""


class _CheckOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[_CheckRow]


class OpenAICompatChecker(_Base):
    purpose: Purpose = "check"

    def check(self, req: CheckRequest) -> tuple[list[CheckResult], list[Usage]]:
        try:
            res = self._call(
                build_check_messages(req),
                check_response_format(req, strict=self._strict),
                _CheckOut,
            )
        except AiError as exc:
            raise to_job_error(exc, "check") from exc
        allowed = {i.ref for i in req.items}
        out: dict[str, CheckResult] = {}
        for row in res.value.results:
            if row.ref not in allowed or row.ref in out:  # unknown refs dropped, first one wins
                continue
            out[row.ref] = CheckResult(ref=row.ref, kind=row.kind, phrase=row.phrase or None)
        return list(out.values()), res.usages


class _SelectOut(SelectOutput):
    model_config = ConfigDict(extra="forbid")


class OpenAICompatSelector(_Base):
    purpose: Purpose = "qa_select"

    def select(self, req: SelectRequest) -> tuple[SelectOutput, list[Usage]]:
        try:
            res = self._call(
                build_select_messages(req),
                select_response_format(req, strict=self._strict),
                _SelectOut,
            )
        except AiError as exc:
            raise to_job_error(exc, "qa_select") from exc
        return SelectOutput(refs=list(res.value.refs)), res.usages
