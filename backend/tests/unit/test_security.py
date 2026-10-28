"""UT-SEC-01..08: security primitives and rate limiter (07 section 3.3)."""

from __future__ import annotations

import hashlib
import hmac
import re
from datetime import date
from types import SimpleNamespace

import pytest

from app.clock import FakeClock
from app.errors import Unauthenticated

SECRET = "s" * 40


def test_ut_sec_01_password_hasher():
    from app.security.passwords import PasswordHasher

    h = PasswordHasher()
    a = h.hash("correct horse")
    b = h.hash("correct horse")
    assert a.startswith("$argon2id$")
    assert a != b  # salted
    assert h.verify(a, "correct horse") is True
    assert h.verify(a, "wrong") is False
    assert h.verify("not-a-hash", "x") is False
    assert h.needs_rehash(a) is False


def test_ut_sec_01_needs_rehash_for_weaker_params():
    from argon2 import PasswordHasher as Raw

    from app.security.passwords import PasswordHasher

    weak = Raw(time_cost=1, memory_cost=8, parallelism=1).hash("pw")
    assert PasswordHasher().needs_rehash(weak) is True


def test_ut_sec_02_cookie_round_trip():
    from app.security.cookies import SessionCookieCodec

    clock = FakeClock()
    codec = SessionCookieCodec(SECRET, clock)
    issued = codec.issue("member-1", 3)
    payload = codec.parse(issued.value)
    assert payload.member_id == "member-1"
    assert payload.session_epoch == 3
    assert payload.issued_at == int(clock.now().timestamp())
    assert re.fullmatch(r"[0-9a-f]{32}", payload.sid)
    other = codec.parse(codec.issue("member-1", 3).value)
    assert other.sid != payload.sid


def test_ut_sec_03_tampered_cookie_rejected():
    from app.security.cookies import SessionCookieCodec

    codec = SessionCookieCodec(SECRET, FakeClock())
    value = codec.issue("m", 1).value
    # Flip a middle character of the signature: the last base64 character
    # carries padding bits, so changing it can decode to the same bytes.
    i = len(value) - 5
    flipped = value[:i] + ("A" if value[i] != "A" else "B") + value[i + 1 :]
    for bad in (flipped, "", "garbage", value + "x", "a." + value):
        with pytest.raises(Unauthenticated):
            codec.parse(bad)


def test_ut_sec_03_expired_cookie_rejected():
    from app.security.cookies import SessionCookieCodec

    clock = FakeClock()
    codec = SessionCookieCodec(SECRET, clock)
    value = codec.issue("m", 1).value
    clock.advance(7 * 86400 - 5)
    assert codec.parse(value).member_id == "m"
    clock.advance(10)
    with pytest.raises(Unauthenticated):
        codec.parse(value)


def test_ut_sec_03_wrong_key_rejected():
    from app.security.cookies import SessionCookieCodec

    clock = FakeClock()
    value = SessionCookieCodec(SECRET, clock).issue("m", 1).value
    with pytest.raises(Unauthenticated):
        SessionCookieCodec("t" * 40, clock).parse(value)


def test_ut_sec_03_visitor_cookie_helpers():
    from app.security.cookies import is_valid_visitor_id, new_visitor_id

    v = new_visitor_id()
    assert re.fullmatch(r"[0-9a-f]{32}", v)
    assert v != new_visitor_id()
    assert is_valid_visitor_id(v)
    assert not is_valid_visitor_id("x" * 32)
    assert not is_valid_visitor_id("")


def test_ut_sec_04_csrf_token():
    from app.security.csrf import CsrfTokenService

    svc = CsrfTokenService(SECRET)
    ta, tb = svc.token_for("sid-a"), svc.token_for("sid-b")
    expected = hmac.new(SECRET.encode(), b"csrf:sid-a", hashlib.sha256).hexdigest()
    assert ta == expected
    assert svc.verify("sid-a", ta) is True
    assert svc.verify("sid-b", ta) is False
    assert svc.verify("sid-b", tb) is True
    assert svc.verify("sid-a", "") is False
    assert svc.verify("sid-a", None) is False


def test_ut_sec_04_csrf_uses_constant_time_compare(monkeypatch):
    import app.security.csrf as mod

    calls = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append(1)
        return real(a, b)

    monkeypatch.setattr(mod.hmac, "compare_digest", spy)
    mod.CsrfTokenService(SECRET).verify("sid", "abc")
    assert calls


def _req(xff: str | None, host: str | None = "9.9.9.9"):
    headers = {"x-forwarded-for": xff} if xff is not None else {}
    client = SimpleNamespace(host=host) if host else None
    return SimpleNamespace(headers=headers, client=client)


def test_ut_sec_05_trusted_proxy_uses_last_hop():
    from app.security.client_ip import ClientIpResolver

    r = ClientIpResolver(trusted_proxy=True)
    assert r.resolve(_req("1.1.1.1, 2.2.2.2, 3.3.3.3")) == "3.3.3.3"
    assert r.resolve(_req(" 4.4.4.4 ")) == "4.4.4.4"
    # header absent: fall back to the socket address
    assert r.resolve(_req(None)) == "9.9.9.9"


def test_ut_sec_05_untrusted_proxy_ignores_header():
    from app.security.client_ip import ClientIpResolver

    r = ClientIpResolver(trusted_proxy=False)
    assert r.resolve(_req("1.1.1.1, 2.2.2.2, 3.3.3.3")) == "9.9.9.9"
    assert r.resolve(_req(None, host=None)) == "unknown"


def test_ut_sec_06_ip_hasher():
    from app.security.client_ip import IpHasher

    h = IpHasher("ip-key")
    d1, d2 = date(2026, 10, 28), date(2026, 10, 29)
    a, b = h.hash("1.2.3.4", d1), h.hash("1.2.3.4", d2)
    assert a != b
    assert a == h.hash("1.2.3.4", d1)
    assert re.fullmatch(r"[0-9a-f]{64}", a)
    assert "1.2.3.4" not in a
    assert a != IpHasher("other").hash("1.2.3.4", d1)
    assert a == hmac.new(b"ip-key", b"1.2.3.4" + b"2026-10-28", hashlib.sha256).hexdigest()


def test_ut_sec_07_sliding_window():
    from app.security.ratelimit import InMemorySlidingWindow

    clock = FakeClock()
    lim = InMemorySlidingWindow(clock)
    for _ in range(10):
        assert lim.hit("ask", "k", 10, 3600).allowed
    denied = lim.hit("ask", "k", 10, 3600)
    assert denied.allowed is False
    assert denied.retry_after_s > 0
    assert denied.scope == "ask"
    # a denied hit does not extend the window
    clock.advance(3601)
    assert lim.hit("ask", "k", 10, 3600).allowed is True


def test_ut_sec_07_sliding_window_is_sliding_and_keyed():
    from app.security.ratelimit import InMemorySlidingWindow

    clock = FakeClock()
    lim = InMemorySlidingWindow(clock)
    assert lim.hit("s", "a", 2, 60).allowed
    clock.advance(30)
    assert lim.hit("s", "a", 2, 60).allowed
    assert not lim.hit("s", "a", 2, 60).allowed
    assert lim.hit("s", "b", 2, 60).allowed  # other key
    assert lim.hit("t", "a", 2, 60).allowed  # other scope
    clock.advance(31)  # first hit has left the window
    assert lim.hit("s", "a", 2, 60).allowed


def test_ut_sec_07_null_limiter_always_allows():
    from app.security.ratelimit import NullLimiter, RateLimiter

    lim = NullLimiter()
    assert isinstance(lim, RateLimiter)
    assert all(lim.hit("x", "k", 1, 1).allowed for _ in range(5))


def test_ut_sec_08_login_limiter_scopes():
    from app.security.ratelimit import InMemorySlidingWindow

    clock = FakeClock()
    lim = InMemorySlidingWindow(clock)

    def attempt(ip: str, email: str):
        d = lim.hit("ip", ip, 10, 900)
        if not d.allowed:
            return d
        return lim.hit("login", email, 5, 900)

    results = [attempt(f"10.0.0.{i}", "a@x.org") for i in range(6)]
    assert [r.allowed for r in results] == [True] * 5 + [False]
    assert results[5].scope == "login"

    lim2 = InMemorySlidingWindow(clock)

    def attempt2(ip: str, email: str):
        d = lim2.hit("ip", ip, 10, 900)
        if not d.allowed:
            return d
        return lim2.hit("login", email, 5, 900)

    results = [attempt2("10.0.0.1", f"u{i}@x.org") for i in range(11)]
    assert [r.allowed for r in results] == [True] * 10 + [False]
    assert results[10].scope == "ip"
