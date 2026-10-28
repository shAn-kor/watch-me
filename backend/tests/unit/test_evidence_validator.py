"""Unit tests of the pure range rules of the EvidenceValidator (02 I-3, 01 evidence rules)."""

from __future__ import annotations

import pytest

from app.services.evidence_validator import range_problem


@pytest.mark.parametrize(
    ("start", "end", "duration", "ok"),
    [
        (0.0, 1.0, 20.0, True),
        (0.0, 60.0, 100.0, True),
        (19.0, 20.0, 20.0, True),
        (2.0, 2.9, 20.0, False),
        (0.0, 60.1, 100.0, False),
        (15.0, 21.0, 20.0, False),
        (-0.5, 3.0, 20.0, False),
        (5.0, 5.0, 20.0, False),
        (6.0, 5.0, 20.0, False),
        (2.3, 3.3, 20.0, True),  # 0.1 s grid noise
        (0.0, 20.04, 20.0, True),  # rounds to 20.0
    ],
)
def test_range_problem(start, end, duration, ok):
    assert (range_problem(start, end, duration) is None) is ok
