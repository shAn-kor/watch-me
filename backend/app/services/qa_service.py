"""Public Q&A: `QAService.ask` (01 section 6.2, 03 section 7).

The model only chooses among numbered facts (refs). Every word the visitor reads is
a fact's own text or a fixed template. Order of checks: dog, question, limits,
health keywords, facts, cost cap, selector call, mapping, render.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from app.ai.types import SelectRequest, Usage
from app.clock import Clock
from app.db.uow import UowFactory
from app.domain.health import HealthQuestionMatcher
from app.errors import (
    JobError,
    NotFound,
    QaCostCapReached,
    QaUnavailable,
    QuestionTooShort,
    ValidationFailed,
)
from app.repositories.cost_ledger import CostLedgerRepository
from app.repositories.public_facts import PublicDog, get_public_dog, public_facts
from app.repositories.qa_log import QaLogRepository
from app.services.qa_alias import AliasMapper
from app.services.qa_limits import QaLimiter
from app.services.qa_render import AnswerRenderer, QaAnswer, QaContact
from app.services.views import MediaUrls


@dataclass(frozen=True, slots=True)
class Visitor:
    """The raw IP lives in memory for the length of one call: it is hashed at once
    and never logged or stored (I-18)."""

    ip: str
    cookie_id: str


class QAService:
    def __init__(
        self,
        *,
        uow_factory: UowFactory,
        clock: Clock,
        selector: Any,
        health: HealthQuestionMatcher,
        ip_hasher: Any,
        media_urls: MediaUrls,
        limiter: QaLimiter,
        cap_guard: Any,
        max_facts: int = 5,
        min_chars: int = 3,
        max_chars: int = 300,
        ledger_purpose: str = "qa_select",
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._selector = selector
        self._health = health
        self._ip_hasher = ip_hasher
        self._limiter = limiter
        self._cap_guard = cap_guard
        self._mapper = AliasMapper(max_facts)
        self._renderer = AnswerRenderer(media_urls)
        self._min = min_chars
        self._max = max_chars
        self._purpose = ledger_purpose

    # ------------------------------------------------------------------ ask

    def ask(self, slug: str, question: str, visitor: Visitor) -> QaAnswer:
        started = perf_counter()
        text = unicodedata.normalize("NFC", question).strip()
        with self._uow() as u:
            session = u.session
            dog = get_public_dog(session, slug)
            if dog is None:
                raise NotFound()
            self._validate(text)
            ip_hash = self._ip_hasher.hash(visitor.ip, self._clock.now().date())
            self._limiter.check(session, ip_hash, visitor.cookie_id)
            log = _Log(self, session, dog, text, ip_hash, visitor.cookie_id, started)

            if self._health.matches(text):
                answer = self._renderer.health_redirect(
                    QaContact(dog.contact_url, dog.contact_email, dog.contact_phone)
                )
                return log.finish(u, answer)

            facts = public_facts(session, dog.id)
            if not facts:
                return log.finish(u, self._renderer.not_observed())

            try:
                self._cap_guard.ensure_below_cap(session)
            except QaCostCapReached:
                log.record("error")
                u.commit()
                raise

            table = self._mapper.build(facts)
            request = SelectRequest(
                question=text,
                facts=table.fact_refs,
                max_refs=self._mapper._max_facts,  # noqa: SLF001
            )
            try:
                output, usages = self._selector.select(request)
            except JobError as exc:
                log.ledger_id = log.write_usages(exc.usages)
                log.record("error")
                u.commit()
                raise QaUnavailable() from exc

            log.ledger_id = log.write_usages(usages)
            selection = self._mapper.resolve(table, output.refs)
            log.dropped = selection.dropped
            fresh = {f.id: f for f in public_facts(session, dog.id)}
            chosen = [fresh[i] for i in selection.in_profile_order if i in fresh]
            if not chosen:
                return log.finish(u, self._renderer.not_observed())
            return log.finish(u, self._renderer.answered(chosen))

    # -------------------------------------------------------------- helpers

    def _validate(self, text: str) -> None:
        if len(text) < self._min:
            raise QuestionTooShort()
        if len(text) > self._max:
            raise ValidationFailed(
                details={
                    "fields": [{"path": "question", "problem": "too_long", "limit": self._max}]
                }
            )


class _Log:
    """The one `qa_log` row of a call, plus its ledger rows."""

    def __init__(
        self,
        svc: QAService,
        session: Any,
        dog: PublicDog,
        question: str,
        ip_hash: str,
        cookie_id: str,
        started: float,
    ) -> None:
        self._svc = svc
        self._session = session
        self._dog = dog
        self._question = question
        self._ip_hash = ip_hash
        self._cookie_id = cookie_id
        self._started = started
        self.ledger_id: int | None = None
        self.dropped = 0
        self.fact_ids: list[str] = []

    def write_usages(self, usages: Any) -> int | None:
        repo = CostLedgerRepository(self._session)
        last: int | None = None
        for usage in usages:
            usage = Usage.model_validate(usage) if not isinstance(usage, Usage) else usage
            last = repo.add_usage(
                usage,
                purpose=self._svc._purpose,  # noqa: SLF001
                dog_id=self._dog.id,
                now=self._svc._clock.now(),  # noqa: SLF001
            )
        return last

    def record(self, outcome: str) -> None:
        QaLogRepository(self._session).add(
            dog_id=self._dog.id,
            ip_hash=self._ip_hash,
            cookie_id=self._cookie_id,
            question=self._question,
            outcome=outcome,
            fact_ids=self.fact_ids,
            dropped_ids=self.dropped,
            ledger_id=self.ledger_id,
            latency_ms=int((perf_counter() - self._started) * 1000),
            now=self._svc._clock.now(),  # noqa: SLF001
        )

    def finish(self, u: Any, answer: QaAnswer) -> QaAnswer:
        self.fact_ids = list(answer.cited_fact_ids)
        self.record(answer.outcome)
        remaining = self._svc._limiter.remaining(  # noqa: SLF001
            self._session, self._ip_hash, self._cookie_id
        )
        u.commit()
        return answer.with_remaining(remaining)
