"""The 01-api-spec.md section 1.2 error catalog as data: (http_status, code).

Single copy for UT-META-01. A test cross-checks it against the spec file when
the docs directory is present, so the two cannot drift silently.
"""

from __future__ import annotations

CATALOG: tuple[tuple[int, str], ...] = (
    (400, "malformed_request"),
    (400, "upload_incomplete"),
    (401, "unauthenticated"),
    (401, "invalid_credentials"),
    (403, "csrf_failed"),
    (403, "forbidden_role"),
    (403, "consent_required"),
    (403, "not_own_session"),
    (403, "staff_only_situation"),
    (404, "not_found"),
    (409, "invalid_state"),
    (409, "clip_limit_reached"),
    (409, "clip_not_ready"),
    (409, "playback_required"),
    (409, "flags_unacknowledged"),
    (409, "publish_checklist_incomplete"),
    (413, "file_too_large"),
    (415, "unsupported_file_type"),
    (415, "unsupported_media_type"),
    (422, "validation_error"),
    (422, "clip_too_long"),
    (422, "evidence_out_of_range"),
    (422, "question_too_short"),
    (429, "rate_limited"),
    (500, "internal_error"),
    (503, "qa_cost_cap_reached"),
    (503, "qa_unavailable"),
    (503, "storage_unavailable"),
    (503, "service_busy"),
)

CODES: frozenset[str] = frozenset(code for _, code in CATALOG)
