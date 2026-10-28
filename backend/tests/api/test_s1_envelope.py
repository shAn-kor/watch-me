"""API-ENV, API-HLTH, API-ORG, API-ROLE (07 section 3.7)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from tests.api._s1_support import build_probe_router, csrf


@pytest.fixture
def world(seed):
    return seed.standard_world()


@pytest.fixture
def probed_app(app):
    app.include_router(build_probe_router())
    return app


# ------------------------------------------------------------------ API-ENV


def test_api_env_01_error_envelope_404(client):
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404
    body = r.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == "not_found"
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    assert body["error"]["details"] == {}


def test_api_env_01_error_envelope_422(client):
    r = client.post("/api/auth/login", json={"email": "", "password": "x" * 2000})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error"
    fields = err["details"]["fields"]
    assert fields and all({"path", "problem"} <= set(f) for f in fields)
    by_path = {f["path"]: f for f in fields}
    assert by_path["body.email"]["problem"] == "too_short"
    assert by_path["body.email"]["limit"] == 1
    assert by_path["body.password"]["problem"] == "too_long"
    assert isinstance(by_path["body.password"]["limit"], int)


def test_api_env_01_error_envelope_500(probed_app):
    with TestClient(probed_app, raise_server_exceptions=False) as c:
        r = c.get("/api/_t/boom")
    assert r.status_code == 500
    err = r.json()["error"]
    assert err["code"] == "internal_error"
    assert set(err) == {"code", "message", "details"}
    request_id = r.headers["X-Request-Id"]
    assert request_id and err["details"]["request_id"] == request_id
    assert "Traceback" not in r.text and "secret internal detail" not in r.text
    assert "RuntimeError" not in r.text


def test_api_env_02_api_responses_are_no_store(client, world, login_as):
    login_as(world.vol1)
    for path in ("/api/me", "/api/does-not-exist"):
        assert client.get(path).headers["Cache-Control"] == "no-store", path
    client.cookies.clear()
    assert client.get("/api/me").headers["Cache-Control"] == "no-store"  # a 401 too


@pytest.fixture
def spa_dir(tmp_path):
    d = tmp_path / "spa"
    d.mkdir()
    (d / "index.html").write_text("<!doctype html><title>Watch Me</title><div id=root></div>")
    (d / "favicon.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    return d


def test_api_env_03_spa_shell_is_the_same_for_every_slug(container, spa_dir, world):
    from app.main import create_app

    app = create_app(container, spa_dir=spa_dir)
    slugs = {
        "published": world.dog_pub.public_slug,
        "adopted": world.dog_adopted.public_slug,
        "unknown": "zzzzzzzzzzzz",
        "deleted": "deleteddogxx",  # a tombstone has no slug; any string behaves as unknown
    }
    index = (spa_dir / "index.html").read_text()
    with TestClient(app) as c:
        bodies = set()
        for kind, slug in slugs.items():
            r = c.get(f"/d/{slug}")
            assert r.status_code == 200, kind
            assert r.text == index, kind
            assert r.headers["X-Robots-Tag"] == "noindex", kind
            assert "text/html" in r.headers["content-type"], kind
            bodies.add(r.text)
        assert len(bodies) == 1
        for path in ("/app/dogs/x", "/terms", "/some/unknown/path", "/"):
            r = c.get(path)
            assert r.status_code == 200 and r.text == index, path
        r = c.get("/favicon.svg")  # a real file of the build is served as itself
        assert r.status_code == 200 and "svg" in r.text
        assert c.get("/..%2f..%2fetc/passwd").text == index  # no path traversal

        r = c.get("/api/unknown")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "not_found"
        r = c.get("/media/unknown.mp4")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "not_found"
        r = c.get("/api")
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_api_env_03_security_headers(container, spa_dir):
    from app.main import create_app

    with TestClient(create_app(container, spa_dir=spa_dir)) as c:
        r = c.get("/terms")
        assert r.headers["X-Content-Type-Options"] == "nosniff"
        assert "X-Robots-Tag" not in r.headers  # noindex only on profile routes
        assert c.get("/api/unknown").headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.xfail(reason="needs lane S5: GET /api/public/dogs/{slug}", strict=False)
def test_api_env_03_public_api_404_for_hidden_and_unknown_slugs(client, world):
    ok = client.get(f"/api/public/dogs/{world.dog_pub.public_slug}")
    assert ok.status_code == 200
    unknown = client.get("/api/public/dogs/zzzzzzzzzzzz")
    assert unknown.status_code == 404 and unknown.json()["error"]["code"] == "not_found"
    for slug in (world.dog_adopted.public_slug, "deleteddogxx"):
        r = client.get(f"/api/public/dogs/{slug}")
        assert r.status_code == 404
        assert r.json() == unknown.json()


# ----------------------------------------------------------------- API-HLTH


def test_api_hlth_01_healthz_ignores_ai(app, container):
    class Boom:
        def __getattr__(self, name):
            raise AssertionError("health must not call AI providers")

    container.ai.transcriber = container.ai.drafter = Boom()
    container.ai.checker = container.ai.selector = Boom()
    with TestClient(app) as c:
        r = c.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_api_hlth_01_db_down_gives_503(app, container):
    class DownUow:
        def __enter__(self):
            raise OperationalError("SELECT 1", {}, Exception("database is down"))

        def __exit__(self, *exc):
            return None

    container.uow_factory = DownUow
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/healthz")
    assert r.status_code == 503
    assert r.json() == {"status": "unavailable"}
    assert "database is down" not in r.text


# ------------------------------------------------------------------ API-ORG


def test_api_org_01_cross_org_is_not_found(client, probed_app, world, login_as):
    token = login_as(world.staff_b)
    dog_a = world.dog_review.id
    for method in ("GET", "PATCH", "PUT", "POST", "DELETE"):
        r = client.request(method, f"/api/_t/dogs/{dog_a}", headers=csrf(token))
        assert r.status_code == 404, method
        assert r.json()["error"]["code"] == "not_found", method
    own = client.get(f"/api/_t/dogs/{world.dog_b.id}")
    assert own.status_code == 200  # the allowed row next to the denied rows
    missing = client.get("/api/_t/dogs/" + "0" * 32)
    assert missing.json() == client.get(f"/api/_t/dogs/{dog_a}").json()  # same body


def test_api_org_01_member_of_org_a_is_allowed(client, probed_app, world, login_as):
    token = login_as(world.vol1)
    for method in ("GET", "PATCH", "PUT", "POST", "DELETE"):
        r = client.request(method, f"/api/_t/dogs/{world.dog_review.id}", headers=csrf(token))
        assert r.status_code == 200, method


def test_api_org_01_every_real_creator_route(client, probed_app, world, login_as):
    from tests.api._s1_support import iter_api_routes, uses_principal

    ids = {
        "dog_id": world.dog_review.id,
        "session_id": world.session_review.id,
        "clip_id": world.clips_review[0].id,
        "fact_id": world.facts_review[0].id,
    }
    token = login_as(world.staff_b)
    checked = 0
    for full_path, route in iter_api_routes(probed_app.router):
        if "/_t/" in full_path or not full_path.startswith("/api/"):
            continue
        if not uses_principal(route.dependant) or not any(k in full_path for k in ids):
            continue
        path = full_path
        for key, value in ids.items():
            path = path.replace("{" + key + "}", value)
        for method in route.methods - {"HEAD", "OPTIONS"}:
            r = client.request(method, path, headers=csrf(token), json={})
            assert r.status_code == 404 and r.json()["error"]["code"] == "not_found", (method, path)
            checked += 1
    assert checked > 0


@pytest.mark.xfail(reason="needs lane S5: /media routes", strict=False)
def test_api_org_01_media_with_other_org_cookie(app, client, world, login_as):
    from tests.api._s1_support import iter_api_routes

    assert any(p.startswith("/media/") for p, _ in iter_api_routes(app.router)), "no media route"
    login_as(world.staff_b)
    r = client.get(f"/media/{world.clips_review[0].id}.mp4")
    assert r.status_code == 404


# ----------------------------------------------------------------- API-ROLE


def test_api_role_01_staff_only_dependency(client, probed_app, world, login_as):
    token = login_as(world.vol1)
    r = client.post("/api/_t/staff", headers=csrf(token))
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden_role"
    token = login_as(world.staff1)
    assert client.post("/api/_t/staff", headers=csrf(token)).status_code == 200


def test_api_role_01_role_check_follows_cookie_and_csrf(client, probed_app, world, login_as):
    token = login_as(world.vol1)
    r = client.post("/api/_t/staff")  # no CSRF header: csrf_failed comes before the role
    assert r.json()["error"]["code"] == "csrf_failed"
    client.cookies.clear()
    r = client.post("/api/_t/staff", headers=csrf(token))
    assert r.json()["error"]["code"] == "unauthenticated"


_STAFF_ROUTES = [
    pytest.param("PUT", "/api/dogs/{dog}/publish-checklist", id="checklist"),
    pytest.param("POST", "/api/dogs/{dog}/publish", id="publish"),
    pytest.param("POST", "/api/dogs/{dog}/unpublish", id="unpublish"),
    pytest.param("POST", "/api/dogs/{dog}/adopted", id="adopted"),
    pytest.param("DELETE", "/api/dogs/{dog}", id="delete-dog"),
    pytest.param(
        "GET",
        "/api/admin/metrics",
        id="admin-metrics",
        marks=pytest.mark.xfail(reason="needs phase 3: admin metrics route", strict=False),
    ),
]


@pytest.mark.parametrize(("method", "path"), _STAFF_ROUTES)
def test_api_role_01_real_staff_routes(client, world, login_as, method, path):
    token = login_as(world.vol1)
    r = client.request(method, path.format(dog=world.dog_ready.id), json={}, headers=csrf(token))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden_role"


# ------------------------------------------------------------------ extras


def test_limit_writes_per_member(client, probed_app, container, world, login_as, clock):
    login_as(world.vol1)
    limit = container.settings.rate_writes_per_member_min
    for _ in range(limit):
        assert client.get("/api/_t/limited-writes").status_code == 200
    r = client.get("/api/_t/limited-writes")
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"
    assert r.json()["error"]["details"]["scope"] == "member"
    assert int(r.headers["Retry-After"]) >= 1
    clock.advance(61)
    assert client.get("/api/_t/limited-writes").status_code == 200
    login_as(world.vol2)  # another member has their own budget
    assert client.get("/api/_t/limited-writes").status_code == 200
