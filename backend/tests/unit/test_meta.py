"""UT-META-01: every code in the 01 error catalog is implemented and asserted."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.error_catalog import CATALOG, CODES

BACKEND = Path(__file__).resolve().parents[2]
SPEC = BACKEND.parent / "docs" / "design" / "01-api-spec.md"


def test_ut_meta_01_catalog_matches_spec_file():
    if not SPEC.exists():
        pytest.skip("docs/design/01-api-spec.md not present")
    text = SPEC.read_text(encoding="utf-8")
    start = text.index("### 1.2 Error code catalog")
    end = text.index("### 1.3 Rate limits")
    rows = re.findall(r"^\|\s*(\d{3})\s*\|\s*`([a-z_]+)`", text[start:end], re.MULTILINE)
    assert tuple((int(s), c) for s, c in rows) == CATALOG


def test_ut_meta_01_every_code_has_an_app_error_class():
    from app.errors import ERROR_CLASSES, AppError

    assert set(ERROR_CLASSES) == set(CODES)
    for status, code in CATALOG:
        cls = ERROR_CLASSES[code]
        assert issubclass(cls, AppError)
        assert cls.code == code
        assert cls.http_status == status


def test_ut_meta_01_app_error_carries_code_status_details():
    from app.errors import NotFound, PlaybackRequired

    err = PlaybackRequired(details={"missing_evidence_ids": ["a"]})
    assert (err.code, err.http_status) == ("playback_required", 409)
    assert err.details == {"missing_evidence_ids": ["a"]}
    assert NotFound().details == {}
    assert err.to_envelope()["error"]["code"] == "playback_required"
    assert err.to_envelope()["error"]["details"] == {"missing_evidence_ids": ["a"]}


def test_ut_meta_01_job_error_shape():
    from app.errors import JobError

    err = JobError("ai_failed", True, retry_after_s=30.0)
    assert (err.code, err.retryable, err.retry_after_s, err.usages) == (
        "ai_failed",
        True,
        30.0,
        (),
    )
    assert not hasattr(err, "fail_code")


def test_ut_meta_01_every_code_is_asserted_in_api_tests():
    asserted: set[str] = set()
    for path in (BACKEND / "tests" / "api").rglob("test_*.py"):
        text = path.read_text(encoding="utf-8")
        asserted.update(c for c in CODES if re.search(rf"[\"']{c}[\"']", text))
    missing = sorted(CODES - asserted)
    assert not missing, f"codes never asserted in tests/api: {missing}"
