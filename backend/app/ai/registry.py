"""`AiRegistry`: the one place that turns `AI_*` settings into adapter objects
(06 section 3.3, 04 section 8.6). The container calls `from_settings` once.
"""

from __future__ import annotations

from app.ai.adapters.mock import MockAdapter
from app.ai.adapters.muse_transcribe import MuseTranscriber
from app.ai.adapters.openai_compat import (
    OpenAICompatChecker,
    OpenAICompatDrafter,
    OpenAICompatSelector,
    build_chat_client,
)
from app.ai.adapters.rules import RulesChecker
from app.ai.cost import PriceTable
from app.ai.protocols import FactDrafter, FactSelector, Transcriber, WordingChecker
from app.config import Settings


class AiConfigError(ValueError):
    """The AI configuration cannot start the app (startup check, NFR-5)."""


class AiRegistry:
    def __init__(
        self,
        *,
        transcriber: Transcriber,
        drafter: FactDrafter,
        checker: WordingChecker,
        selector: FactSelector,
    ):
        self._transcriber = transcriber
        self._drafter = drafter
        self._checker = checker
        self._selector = selector

    def transcriber(self) -> Transcriber:
        return self._transcriber

    def drafter(self) -> FactDrafter:
        return self._drafter

    def checker(self) -> WordingChecker:
        return self._checker

    def selector(self) -> FactSelector:
        return self._selector

    @classmethod
    def from_settings(cls, settings: Settings) -> AiRegistry:
        forbidden = settings.forbidden_contributor_models()
        if forbidden:
            raise AiConfigError(
                "a contributor-tier model may train on clips (NFR-5); refusing "
                f"{forbidden}. Set AI_ALLOW_CONTRIBUTOR_MODEL=true only if that is intended."
            )
        mock = MockAdapter(settings.ai_mock_fixtures_dir)  # one instance: faults count once
        prices: PriceTable | None = None

        def price_table() -> PriceTable:
            nonlocal prices
            if prices is None:
                prices = PriceTable.from_file(settings.ai_prices_file)
            return prices

        def chat(role: str, stream: bool = False):
            conn = settings.ai_connection(role)  # type: ignore[arg-type]
            if not conn.api_key:
                raise AiConfigError(
                    f"AI_{role.upper()}={getattr(settings, f'ai_{role}')} needs AI_API_KEY "
                    f"(or AI_{role.upper()}_API_KEY)"
                )
            return build_chat_client(conn, timeout_s=settings.ai_timeout_s, stream=stream)

        strict = settings.ai_schema_strict

        if settings.ai_transcriber == "mock":
            transcriber: Transcriber = mock
        elif settings.ai_transcriber == "muse_transcribe":
            conn = settings.ai_connection("transcriber")
            if not conn.api_key:
                raise AiConfigError(
                    "AI_TRANSCRIBER=muse_transcribe needs AI_API_KEY (or AI_TRANSCRIBER_API_KEY)"
                )
            transcriber = MuseTranscriber(conn, price_table(), timeout_s=settings.ai_timeout_s)
        else:
            raise AiConfigError(
                f"AI_TRANSCRIBER={settings.ai_transcriber} is not built yet; use mock"
            )

        drafter: FactDrafter = (
            mock
            if settings.ai_drafter == "mock"
            else OpenAICompatDrafter(
                chat("drafter", stream=settings.ai_stream), price_table(), strict=strict
            )
        )
        checker: WordingChecker
        if settings.ai_checker == "mock":
            checker = mock
        elif settings.ai_checker == "rules":
            checker = RulesChecker()
        else:
            checker = OpenAICompatChecker(chat("checker"), price_table(), strict=strict)
        selector: FactSelector = (
            mock
            if settings.ai_selector == "mock"
            else OpenAICompatSelector(chat("selector"), price_table(), strict=strict)
        )
        return cls(transcriber=transcriber, drafter=drafter, checker=checker, selector=selector)
