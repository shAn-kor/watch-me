"""API-AUTH, API-CNS, API-CSRF (07 section 3.7)."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.models import Member
from tests.api._s1_support import UNSAFE, build_probe_router, creator_unsafe_routes, csrf
from tests.factories import TEST_PASSWORD

# ---------------------------------------------------------------- fixtures


@pytest.fixture
def world(seed):
    return seed.standard_world()


@pytest.fixture
def probed_app(app):
    app.include_router(build_probe_router())
    return app


@pytest.fixture
def https_client(settings, app):
    """Client on https so a `Secure` cookie travels (cookie_secure=True)."""
    settings.cookie_secure = True
    with TestClient(app, base_url="https://testserver") as c:
        yield c


@pytest.fixture
def proxy_client(settings, container, clock):
    """App behind a trusted proxy so tests can vary the client IP per request."""
    settings.trusted_proxy = True
    from app.container import build_container
    from app.main import create_app

    c2 = build_container(settings, clock=clock, engine=container.engine, ai=container.ai)
    with TestClient(create_app(c2)) as c:
        yield c


def _login(client, email, password=TEST_PASSWORD, **kw):
    return client.post("/api/auth/login", json={"email": email, "password": password}, **kw)


def _set_cookie_line(response, name="wm_session") -> str:
    lines = [v for k, v in response.headers.multi_items() if k.lower() == "set-cookie"]
    for line in lines:
        if line.startswith(f"{name}="):
            return line
    raise AssertionError(f"no Set-Cookie for {name}: {lines}")


# ------------------------------------------------------------------ API-AUTH


def test_api_auth_01_login_ok(https_client, world):
    r = _login(https_client, world.vol1.email)
    assert r.status_code == 200
    line = _set_cookie_line(r).lower()
    assert "httponly" in line
    assert "secure" in line
    assert "samesite=lax" in line
    assert "path=/" in line
    assert "max-age=604800" in line
    body = r.json()
    assert set(body) == {"member", "org", "csrf_token"}
    assert body["member"]["id"] == world.vol1.id
    assert body["member"]["email"] == world.vol1.email
    assert body["member"]["role"] == "volunteer"
    assert set(body["member"]) == {
        "id",
        "email",
        "display_name",
        "role",
        "consented_at",
        "consent_version",
    }
    assert body["org"]["id"] == world.org_a.id
    assert body["org"]["name"] == "Maple Street Rescue"
    assert set(body["org"]) == {"id", "name", "country", "location", "contact"}
    assert "verified" not in body["org"]
    assert set(body["org"]["contact"]) == {"url", "email", "phone"}
    assert re.fullmatch(r"[0-9a-f]{64}", body["csrf_token"])
    assert "password" not in r.text and "hash" not in r.text
    assert r.headers["Cache-Control"] == "no-store"


def test_api_auth_02_login_failure_shape(client, world):
    wrong = _login(client, world.vol1.email, "not-the-password")
    unknown = _login(client, "nobody@example.test")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["code"] == "invalid_credentials"
    assert wrong.json() == unknown.json()
    assert "wm_session" not in wrong.headers.get("set-cookie", "")


def test_api_auth_03_login_rate_limit(proxy_client, world, clock):
    def attempt(email, ip):
        return _login(proxy_client, email, "wrong-password", headers={"X-Forwarded-For": ip})

    # 10 per IP: the 11th attempt from one IP (different emails) is limited by IP.
    for i in range(10):
        assert attempt(f"u{i}@example.test", "10.0.0.1").status_code == 401
    r = attempt("u99@example.test", "10.0.0.1")
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"
    assert r.json()["error"]["details"]["scope"] == "ip"
    assert int(r.headers["Retry-After"]) >= 1

    # 5 per email: the 6th attempt for one email from different IPs is limited by email.
    for i in range(5):
        assert attempt("same@example.test", f"10.0.1.{i}").status_code == 401
    r = attempt("same@example.test", "10.0.1.99")
    assert r.status_code == 429
    assert r.json()["error"]["details"]["scope"] == "login"
    assert int(r.headers["Retry-After"]) >= 1

    # Both pass again after 15 minutes.
    clock.advance(15 * 60 + 1)
    assert attempt("u99@example.test", "10.0.0.1").status_code == 401
    assert attempt("same@example.test", "10.0.1.99").status_code == 401


def test_api_auth_03_ip_limit_is_checked_before_email_limit(proxy_client, world):
    """Lane B note: a denied per-IP hit must not consume the per-email budget."""
    for i in range(10):
        _login(
            proxy_client,
            f"a{i}@example.test",
            "x",
            headers={"X-Forwarded-For": "10.9.0.1"},
        )
    for _ in range(4):  # limited by IP; none of these may count against the email
        r = _login(proxy_client, "victim@example.test", "x", headers={"X-Forwarded-For": "10.9.0.1"})
        assert r.json()["error"]["details"]["scope"] == "ip"
    for i in range(5):  # the email still has its full budget of 5 from other IPs
        r = _login(proxy_client, "victim@example.test", "x", headers={"X-Forwarded-For": f"10.9.1.{i}"})
        assert r.status_code == 401


def test_ut_arch_03_login_leaves_no_raw_ip_in_logs_or_tables(proxy_client, container, world, caplog):
    """UT-ARCH-03 (login half; the ask half is in test_s6_ask.py): failed and
    successful logins from a known client IP leave that IP in no log line and no row."""
    import logging

    from sqlalchemy import select

    from app.db.base import Base

    ip = "203.0.113.77"
    with caplog.at_level(logging.DEBUG):
        _login(proxy_client, world.vol1.email, "wrong-password", headers={"X-Forwarded-For": ip})
        assert _login(proxy_client, world.vol1.email, headers={"X-Forwarded-For": ip}).status_code == 200
    assert ip not in caplog.text
    with container.engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            for row in conn.execute(select(table)):
                assert ip not in repr(tuple(row)), f"raw IP in {table.name}"


def test_api_auth_04_login_validation(client):
    missing = client.post("/api/auth/login", json={"email": "a@example.test"})
    assert missing.status_code == 422
    err = missing.json()["error"]
    assert err["code"] == "validation_error"
    assert {"path": "body.password", "problem": "required"} in err["details"]["fields"]

    bad_json = client.post(
        "/api/auth/login", content="{not json", headers={"Content-Type": "application/json"}
    )
    assert bad_json.status_code == 400
    assert bad_json.json()["error"]["code"] == "malformed_request"

    form = client.post("/api/auth/login", data={"email": "a@example.test", "password": "x"})
    assert form.status_code == 415
    assert form.json()["error"]["code"] == "unsupported_media_type"


def test_api_auth_05_me(client, container, world, login_as):
    token = login_as(world.vol1)
    r = client.get("/api/me")
    assert r.status_code == 200
    body = r.json()
    assert body["member"]["id"] == world.vol1.id
    assert body["org"]["id"] == world.org_a.id
    assert body["csrf_token"] == token
    assert body["limits"] == {
        "max_clip_bytes": 209715200,
        "max_clip_s": 120,
        "max_clips_per_session": 3,
        "allowed_extensions": [".mp4", ".mov"],
        "wording_check": "rules_only",  # test settings use AI_CHECKER=rules (the default)
    }
    container.settings.ai_checker = "openai_compat"
    assert client.get("/api/me").json()["limits"]["wording_check"] == "model"
    container.settings.ai_checker = "rules"
    assert client.get("/api/me").json()["limits"]["wording_check"] == "rules_only"

    client.cookies.clear()
    r = client.get("/api/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthenticated"


def test_api_auth_06_logout_revokes(client, world, login_as):
    token = login_as(world.vol1)
    old_cookie = client.cookies.get("wm_session")
    assert old_cookie

    no_csrf = client.post("/api/auth/logout")
    assert no_csrf.status_code == 403 and no_csrf.json()["error"]["code"] == "csrf_failed"

    r = client.post("/api/auth/logout", headers=csrf(token))
    assert r.status_code == 204
    assert r.content == b""
    line = _set_cookie_line(r).lower()
    assert "max-age=0" in line or 'wm_session=""' in line or "wm_session=;" in line

    client.cookies.clear()
    client.cookies.set("wm_session", old_cookie)
    r = client.get("/api/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthenticated"


def test_api_auth_06_logout_increments_session_epoch(client, db, world, login_as):
    token = login_as(world.vol1)
    before = db.get(Member, world.vol1.id).session_epoch
    assert client.post("/api/auth/logout", headers=csrf(token)).status_code == 204
    db.rollback()  # end the old read snapshot
    assert db.get(Member, world.vol1.id).session_epoch == before + 1


def test_api_auth_07_tampered_and_expired_cookie(client, world, login_as, clock):
    login_as(world.vol1)
    good = client.cookies.get("wm_session")

    # Flip a middle signature character: the last base64 character carries padding
    # bits, so changing it can decode to the same bytes (same fix as UT-SEC-03).
    i = len(good) - 5
    flipped = good[:i] + ("A" if good[i] != "A" else "B") + good[i + 1 :]
    client.cookies.clear()
    client.cookies.set("wm_session", flipped)
    r = client.get("/api/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthenticated"

    client.cookies.clear()
    client.cookies.set("wm_session", good)
    assert client.get("/api/me").status_code == 200
    clock.advance(days=8)
    r = client.get("/api/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthenticated"


def test_api_auth_08_secure_flag_toggle(settings, container, world, app):
    assert type(settings)(
        _env_file=None,
        secret_key="k" * 32,
        ip_hash_key="x",
        database_url="sqlite://",
    ).cookie_secure is True  # default is secure

    settings.cookie_secure = False
    with TestClient(app) as c:
        r = _login(c, world.vol1.email)
    assert r.status_code == 200
    assert "; secure" not in _set_cookie_line(r).lower()

    settings.cookie_secure = True
    with TestClient(app, base_url="https://testserver") as c:
        r = _login(c, world.vol1.email)
    assert "; secure" in _set_cookie_line(r).lower()


@pytest.mark.parametrize("path", ["/api/members", "/api/auth/register", "/api/auth/signup"])
def test_api_auth_09_no_signup_endpoints(client, path):
    r = client.post(path, json={"email": "x@example.test", "password": "long-enough-1"})
    assert r.status_code in (404, 405)
    assert r.json()["error"]["code"] == "not_found"


# ------------------------------------------------------------------ API-CSRF


def test_api_csrf_01_missing_header(client, probed_app, world, login_as):
    login_as(world.vol1)
    r = client.post("/api/_t/write")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_failed"


def test_api_csrf_01_allowed_row_and_cookie_checked_first(client, probed_app, world, login_as):
    token = login_as(world.vol1)
    assert client.post("/api/_t/write", headers=csrf(token)).status_code == 200
    client.cookies.clear()  # no cookie: 401 comes before the CSRF check
    r = client.post("/api/_t/write")
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthenticated"


def test_api_csrf_02_wrong_and_other_session_token(client, probed_app, world):
    r1 = _login(client, world.vol1.email)
    token_a = r1.json()["csrf_token"]
    cookie_a = client.cookies.get("wm_session")
    r2 = _login(client, world.vol1.email)  # a second session B for the same member
    token_b = r2.json()["csrf_token"]
    assert token_a != token_b
    client.cookies.clear()
    client.cookies.set("wm_session", cookie_a)

    assert client.post("/api/_t/write", headers=csrf(token_b)).json()["error"]["code"] == "csrf_failed"
    assert client.post("/api/_t/write", headers=csrf("0" * 64)).status_code == 403
    assert client.post("/api/_t/write", headers=csrf("")).status_code == 403
    assert client.post("/api/_t/write", headers=csrf(token_a)).status_code == 200


def test_api_csrf_03_all_unsafe_methods_need_the_header(client, probed_app, world, login_as):
    token = login_as(world.vol1)
    routes = creator_unsafe_routes(probed_app)
    methods = {m for m, _ in routes}
    assert methods == set(UNSAFE)  # POST, PUT, PATCH and DELETE all appear
    assert ("POST", "/api/auth/logout") in routes and ("POST", "/api/me/consent") in routes
    for method, path in routes:
        r = client.request(method, path)
        assert r.status_code == 403, (method, path, r.text)
        assert r.json()["error"]["code"] == "csrf_failed", (method, path)
    # GET never needs it.
    assert client.get("/api/_t/open-read").status_code == 200
    assert client.get("/api/me").status_code == 200
    assert token


def test_api_csrf_04_exemptions_login(client, world):
    ok = _login(client, world.vol1.email)  # no X-CSRF-Token
    assert ok.status_code == 200
    bad = _login(client, world.vol1.email, "wrong")
    assert bad.status_code == 401


def test_api_csrf_04_public_route_needs_no_token(client, probed_app):
    r = client.post("/api/_t/public", json={"x": "hi"})
    assert r.status_code == 200


def test_api_csrf_04_public_ask_exempt(client, world):
    r = client.post(
        f"/api/public/dogs/{world.dog_pub.public_slug}/ask", json={"question": "Does he like walks?"}
    )
    assert r.status_code == 200


def test_api_csrf_05_form_post_gets_415(client, probed_app, world, login_as):
    token = login_as(world.vol1)
    r = client.post("/api/me/consent", data={"accepted": "true", "version": "x"}, headers=csrf(token))
    assert r.status_code == 415
    assert r.json()["error"]["code"] == "unsupported_media_type"
    # Cross-site form: no CSRF header at all, still 415 (checked before auth).
    client.cookies.clear()
    r = client.post("/api/me/consent", data={"accepted": "true"})
    assert r.status_code == 415
    # A public route takes JSON only too.
    r = client.post("/api/_t/public", data={"x": "hi"})
    assert r.status_code == 415
    assert r.json()["error"]["code"] == "unsupported_media_type"
    assert client.post("/api/_t/public", json={"x": "a"}).status_code == 200


def test_api_csrf_05_public_ask_form_post(client, world):
    r = client.post(f"/api/public/dogs/{world.dog_pub.public_slug}/ask", data={"question": "hi there"})
    assert r.status_code == 415


# ------------------------------------------------------------------- API-CNS


def _consent(client, token, version, accepted=True):
    return client.post(
        "/api/me/consent",
        json={"accepted": accepted, "version": version},
        headers=csrf(token),
    )


def test_api_cns_01_consent_accept(client, container, world, login_as, clock):
    token = login_as(world.vol_new)
    assert client.get("/api/me").json()["member"]["consented_at"] is None
    r = _consent(client, token, container.settings.consent_version)
    assert r.status_code == 200
    member = r.json()["member"]
    assert member["id"] == world.vol_new.id
    assert member["consented_at"] == "2026-10-28T12:00:00Z"
    assert member["consent_version"] == container.settings.consent_version
    assert client.get("/api/me").json()["member"]["consented_at"] == member["consented_at"]


def test_api_cns_02_consent_validation(client, container, world, login_as):
    token = login_as(world.vol_new)
    r = _consent(client, token, container.settings.consent_version, accepted=False)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    r = _consent(client, token, "1999-01-01")
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error"
    assert err["details"]["fields"][0]["problem"] == "version_mismatch"
    assert client.get("/api/me").json()["member"]["consented_at"] is None


def test_api_cns_03_consent_idempotent(client, container, world, login_as, clock):
    token = login_as(world.vol_new)
    version = container.settings.consent_version
    first = _consent(client, token, version).json()["member"]["consented_at"]
    clock.advance(3600)
    again = _consent(client, token, version).json()["member"]
    assert again["consented_at"] == first
    container.settings.consent_version = "2027-01-01"
    newer = _consent(client, token, "2027-01-01").json()["member"]
    assert newer["consent_version"] == "2027-01-01"
    assert newer["consented_at"] == "2026-10-28T13:00:00Z"


def test_api_cns_04_consent_gate_dependency(client, probed_app, container, world, login_as):
    token = login_as(world.vol_new)
    r = client.post("/api/_t/gated", headers=csrf(token))
    assert r.status_code == 403 and r.json()["error"]["code"] == "consent_required"
    assert _consent(client, token, container.settings.consent_version).status_code == 200
    assert client.post("/api/_t/gated", headers=csrf(token)).status_code == 200


_GATED_REAL = [
    ("POST", "/api/dogs/{dog}/sessions", {"situations": ["leash_walk"], "capture_rules_ack": True}),
    ("POST", "/api/sessions/{session}/clips", None),
    ("POST", "/api/sessions/{session}/submit", None),
    ("POST", "/api/facts/{fact}/confirm", {}),
    ("POST", "/api/dogs/{dog}/facts", {"situation": "food_toys", "behavior": "Dropped the toy twice."}),
]


def test_api_cns_04_consent_gate_on_real_routes(client, container, world, login_as):
    token = login_as(world.vol_new)
    ids = {"dog": world.dog_review.id, "session": world.session_review.id, "fact": world.facts_review[0].id}
    for method, path, body in _GATED_REAL:
        r = client.request(method, path.format(**ids), json=body, headers=csrf(token))
        assert r.status_code == 403 and r.json()["error"]["code"] == "consent_required", (path, r.text)
    assert _consent(client, token, container.settings.consent_version).status_code == 200
    for method, path, body in _GATED_REAL:
        r = client.request(method, path.format(**ids), json=body, headers=csrf(token))
        assert r.json().get("error", {}).get("code") != "consent_required", path


def test_api_cns_05_consent_not_required_for_plain_routes(client, probed_app, world, login_as):
    login_as(world.vol_new)
    assert client.get("/api/_t/open-read").status_code == 200
    assert client.get("/api/me").status_code == 200
    assert client.get(f"/api/_t/dogs/{world.dog_review.id}").status_code == 200


def test_api_cns_05_consent_not_required_on_real_routes(client, world, login_as):
    token = login_as(world.vol_new)
    assert client.get("/api/dogs").status_code == 200
    r = client.post(
        "/api/dogs",
        json={"name": "Rex", "sex": "male", "age_estimate": "2 years", "size": "medium"},
        headers=csrf(token),
    )
    assert r.status_code == 201
    assert client.get(f"/api/sessions/{world.session_review.id}").status_code == 200


def test_api_cns_06_consent_check_precedes_not_found(client, probed_app, container, seed, world, login_as):
    """vol_new (not consented) uploads to an org B session: consent_required, not not_found."""
    sess_b = seed.session(world.dog_b, world.staff_b)
    token = login_as(world.vol_new)
    r = client.post(f"/api/_t/sessions/{sess_b.id}/clips", headers=csrf(token))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "consent_required"

    # After consent the same request is an org-scope miss: not_found.
    assert _consent(client, token, container.settings.consent_version).status_code == 200
    r = client.post(f"/api/_t/sessions/{sess_b.id}/clips", headers=csrf(token))
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
