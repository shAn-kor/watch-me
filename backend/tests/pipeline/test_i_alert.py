"""API-MET-08: the operator alert `ai_auth_error` (04 section 8.7, D2)."""

from __future__ import annotations

import json

import httpx
import pytest

from tests.pipeline.test_p_retry import _setup, _stub_env
from tests.unit.ai_helpers import VALID_DRAFT, FakeHttp, ok


def _alerts(env) -> list[str]:
    with env.api(env.staff) as (client, _):
        r = client.get("/api/admin/metrics")
        assert r.status_code == 200, r.text
        return r.json()["alerts"]


@pytest.mark.parametrize("status", [401, 402, 403])
def test_api_met_08_alert_set_and_clip_fails_at_once(settings, make_env, status):
    http = FakeHttp(httpx.Response(status, json={"error": {"message": "x"}}))
    env = _stub_env(settings, make_env, http)
    dog, vol, sess, clip = _setup(env)
    assert _alerts(env) == []
    env.run()
    row = env.clip(clip.id)
    assert (row.status, row.fail_code) == ("failed", "ai_failed")
    assert row.fail_detail and str(status) in row.fail_detail
    assert http.calls == 1
    assert _alerts(env) == ["ai_auth_error"]


@pytest.mark.parametrize("status", [400, 404, 500])
def test_api_met_08_other_errors_raise_no_alert(settings, make_env, status):
    http = FakeHttp(*[httpx.Response(status, json={"error": {"message": "x"}})] * 2)
    env = _stub_env(settings, make_env, http)
    _setup(env)
    while env.run_step():
        pass
    env.advance(60)
    env.run()
    assert _alerts(env) == []


def test_api_met_08_cleared_by_next_successful_ai_call(settings, make_env):
    http = FakeHttp(
        httpx.Response(401, json={"error": {"message": "x"}}),
        ok(json.dumps(VALID_DRAFT)),
    )
    env = _stub_env(settings, make_env, http)
    dog, vol, sess, clip = _setup(env)
    env.run()
    assert _alerts(env) == ["ai_auth_error"]
    # a later call that reaches the provider and succeeds clears it
    env.advance(60)
    sess2 = env.session(dog, vol)
    clip2 = env.add_clip(sess2, "len_25s.mp4", ordinal=1)
    env.run()
    assert env.clip(clip2.id).status == "ready"
    assert _alerts(env) == []


def test_api_met_08_stays_while_only_failures_follow(settings, make_env):
    http = FakeHttp(
        httpx.Response(401, json={"error": {"message": "x"}}),
        httpx.Response(401, json={"error": {"message": "x"}}),
    )
    env = _stub_env(settings, make_env, http)
    dog, vol, sess, clip = _setup(env)
    env.run()
    env.advance(60)
    sess2 = env.session(dog, vol)
    env.add_clip(sess2, "len_25s.mp4", ordinal=1)
    env.run()
    assert _alerts(env) == ["ai_auth_error"]


