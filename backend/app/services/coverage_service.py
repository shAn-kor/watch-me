"""CoverageService: the single implementation of 02 section 4.1 for the creator list,
the creator detail, publish and the public profile (CAP-2 "same rule as PUB-1").

Every method takes the caller's `UnitOfWork`, so it runs inside the request transaction.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.db.uow import UnitOfWork
from app.domain.coverage import Coverage, compute_coverage
from app.domain.labels import ClipLength, clip_length
from app.domain.ranges import Range
from app.repositories.dogs import DogRepository


@dataclass(frozen=True, slots=True)
class ShortCoverage:
    """The two numbers of `GET /api/dogs` (01 section 4.1)."""

    situations_covered: int
    situations_total: int


class CoverageService:
    def for_dogs(self, uow: UnitOfWork, dog_ids: Sequence[str]) -> dict[str, Coverage]:
        inputs = DogRepository(uow.session).coverage_inputs(list(dog_ids))
        return {d: compute_coverage(facts, clips) for d, (facts, clips) in inputs.items()}

    def for_dog(self, uow: UnitOfWork, dog_id: str) -> Coverage:
        """`Coverage` with 8 entries in PRD order and the `not_observed` list."""
        return self.for_dogs(uow, [dog_id])[dog_id]

    def short_for_dogs(
        self, uow: UnitOfWork, dog_ids: Sequence[str]
    ) -> dict[str, ShortCoverage]:
        return {
            d: ShortCoverage(c.situations_covered, c.situations_total)
            for d, c in self.for_dogs(uow, dog_ids).items()
        }

    @staticmethod
    def clip_length(source: str, evidence: Iterable[Range]) -> ClipLength:
        """Fact clip length label (02 section 4.3)."""
        return clip_length(source, evidence)
