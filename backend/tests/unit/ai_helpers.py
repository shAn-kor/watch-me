"""Shared helpers of the lane C tests: a real `openai` client over an
`httpx.MockTransport` (the fake HTTP boundary; no network), request builders."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import openai

from app.ai.adapters.openai_compat import ChatClient
from app.ai.types import DraftFrame, DraftRequest, TranscriptSegmentOut

MODEL = "muse-spark-1.3"
VALID_DRAFT = {
    "facts": [
        {
            "situation": "new_person",
            "behavior": "Walked to the visitor with a loose wagging tail.",
            "source": "clip",
            "evidence": [{"start_t": 3, "end_t": 9}],
        }
    ]
}


def completion_body(
    content: str | None,
    *,
    finish: str = "stop",
    prompt_tokens: int = 100,
    completion_tokens: int = 10,
    refusal: str | None = None,
    usage: bool = True,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": "cmpl-1",
        "object": "chat.completion",
        "created": 1,
        "model": MODEL,
        "choices": [
            {
                "index": 0,
                "finish_reason": finish,
                "message": {
                    "role": "assistant",
                    "content": content,
                    "refusal": refusal,
                },
            }
        ],
    }
    if usage:
        body["usage"] = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }
    return body


class FakeHttp:
    """Scripted HTTP server: one entry per request, in order. An entry is an
    `httpx.Response`, an exception to raise, or a callable(request)."""

    def __init__(self, *script: Any):
        self.script = list(script)
        self.requests: list[dict[str, Any]] = []

    @property
    def calls(self) -> int:
        return len(self.requests)

    def handler(self, request: httpx.Request) -> httpx.Response:
        try:
            body = json.loads(request.content or b"{}")
        except ValueError:
            body = {}
        self.requests.append(body)
        item = self.script.pop(0)
        if callable(item):
            item = item(request)
        if isinstance(item, BaseException):
            raise item
        return item

    def chat(self, **kw: Any) -> ChatClient:
        sdk = openai.OpenAI(
            base_url="https://ai.invalid/v1",
            api_key="test-key",
            http_client=httpx.Client(transport=httpx.MockTransport(self.handler)),
            max_retries=0,
        )
        return ChatClient(sdk, model=MODEL, **kw)


def ok(content: str, **kw: Any) -> httpx.Response:
    return httpx.Response(200, json=completion_body(content, **kw))


def draft_request(
    tmp_path: Path,
    *,
    n: int = 4,
    k: int = 3,
    transcript: list[TranscriptSegmentOut] | None = None,
    allowed: tuple[str, ...] = ("new_person", "leash_walk"),
    fixture_key: str | None = None,
    mode: str = "frames",
) -> DraftRequest:
    frames = []
    for i in range(n):
        p = tmp_path / f"t{i * k}.jpg"
        p.write_bytes(b"\xff\xd8fake-jpeg" + bytes([i]))
        frames.append(DraftFrame(t=i * k, path=str(p)))
    return DraftRequest(
        mode=mode,  # type: ignore[arg-type]
        clip_ord=1,
        duration_s=float(n * k),
        k=k,
        frames=frames,
        transcript=transcript or [],
        allowed_situations=list(allowed),  # type: ignore[arg-type]
        dog_name="Biscuit",
        observed_on=date(2026, 10, 27),
        fixture_key=fixture_key,
    )


Send = Callable[[list[dict[str, Any]]], Any]
