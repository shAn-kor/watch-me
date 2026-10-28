"""Operations schemas (01 section 8.1)."""

from __future__ import annotations

from pydantic import BaseModel

from app.api.schemas.clips import UtcZ
from app.services.metrics_service import MetricsView


class DraftAcceptanceOut(BaseModel):
    confirmed_ai_unchanged: int
    all_drafts: int
    rate: float


class FactsOut(BaseModel):
    published_dogs: int
    confirmed: int
    with_clip_evidence: int
    clip_evidence_share: float


class TimeOut(BaseModel):
    median_session_to_review_s: int | None
    median_dog_first_session_to_publish_s: int | None


class DogCostOut(BaseModel):
    dog_id: str
    usd: float


class CostOut(BaseModel):
    total_usd: float
    per_dog_usd: list[DogCostOut]
    qa_today_usd: float
    qa_daily_cap_usd: float


class MetricsOut(BaseModel):
    as_of: UtcZ
    draft_acceptance: DraftAcceptanceOut
    facts: FactsOut
    time: TimeOut
    cost: CostOut
    alerts: list[str]
    purge_pending: list[str]

    @classmethod
    def from_view(cls, v: MetricsView) -> MetricsOut:
        return cls(
            as_of=v.as_of,
            draft_acceptance=DraftAcceptanceOut(
                confirmed_ai_unchanged=v.confirmed_ai_unchanged,
                all_drafts=v.all_drafts,
                rate=v.rate,
            ),
            facts=FactsOut(
                published_dogs=v.published_dogs,
                confirmed=v.confirmed,
                with_clip_evidence=v.with_clip_evidence,
                clip_evidence_share=v.clip_evidence_share,
            ),
            time=TimeOut(
                median_session_to_review_s=v.median_session_to_review_s,
                median_dog_first_session_to_publish_s=v.median_dog_first_session_to_publish_s,
            ),
            cost=CostOut(
                total_usd=v.total_usd,
                per_dog_usd=[DogCostOut(dog_id=d, usd=u) for d, u in v.per_dog_usd],
                qa_today_usd=v.qa_today_usd,
                qa_daily_cap_usd=v.qa_daily_cap_usd,
            ),
            alerts=list(v.alerts),
            purge_pending=list(v.purge_pending),
        )


__all__ = ["MetricsOut"]
