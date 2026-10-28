"""AuthService: login, logout, consent, cookie to Principal (06 section 3.2, 3.5).

Combines the security primitives (lane B) with the member table. A method is one
transaction. The service returns frozen views, never ORM rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.clock import Clock
from app.config import Settings
from app.db.uow import UowFactory
from app.errors import (
    InvalidCredentials,
    NotFound,
    RateLimited,
    Unauthenticated,
    ValidationFailed,
)
from app.models import Member, Org
from app.repositories.members import MemberRepository
from app.security.client_ip import IpHasher
from app.security.cookies import CookiePayload, IssuedCookie, SessionCookieCodec
from app.security.csrf import CsrfTokenService
from app.security.passwords import PasswordHasher
from app.security.ratelimit import RateLimiter
from app.services.views import Principal

LOGIN_WINDOW_S = 15 * 60


@dataclass(frozen=True, slots=True)
class MemberView:
    id: str
    email: str
    display_name: str
    role: str
    consented_at: datetime | None
    consent_version: str | None


@dataclass(frozen=True, slots=True)
class ContactView:
    url: str | None
    email: str | None
    phone: str | None


@dataclass(frozen=True, slots=True)
class OrgView:
    id: str
    name: str
    country: str
    location: str
    contact: ContactView


@dataclass(frozen=True, slots=True)
class LoginResult:
    member: MemberView
    org: OrgView
    csrf_token: str
    cookie: IssuedCookie


@dataclass(frozen=True, slots=True)
class MeResult:
    member: MemberView
    org: OrgView
    csrf_token: str


def _member_view(m: Member) -> MemberView:
    return MemberView(
        id=m.id,
        email=m.email,
        display_name=m.display_name,
        role=m.role,
        consented_at=m.consented_at,
        consent_version=m.consent_version,
    )


def _org_view(o: Org) -> OrgView:
    return OrgView(
        id=o.id,
        name=o.name,
        country=o.country,
        location=o.location,
        contact=ContactView(url=o.contact_url, email=o.contact_email, phone=o.contact_phone),
    )


class AuthService:
    def __init__(
        self,
        *,
        uow_factory: UowFactory,
        clock: Clock,
        settings: Settings,
        hasher: PasswordHasher,
        codec: SessionCookieCodec,
        csrf: CsrfTokenService,
        limiter: RateLimiter,
        ip_hasher: IpHasher,
    ):
        self._uow = uow_factory
        self._clock = clock
        self._settings = settings
        self._hasher = hasher
        self._codec = codec
        self._csrf = csrf
        self._limiter = limiter
        self._ip_hasher = ip_hasher
        # Verified against when the email is unknown, so both failures cost the same.
        self._dummy_hash = hasher.hash("watch-me-dummy-password")

    # ------------------------------------------------------------------ login

    def login(self, email: str, password: str, ip: str) -> LoginResult:
        self._enforce_login_limits(email, ip)
        now = self._clock.now()
        with self._uow() as uow:
            members = MemberRepository(uow.session)
            member = members.get_by_email(email)
            if member is None:
                self._hasher.verify(self._dummy_hash, password)
                raise InvalidCredentials()
            if not self._hasher.verify(member.password_hash, password):
                raise InvalidCredentials()
            if self._hasher.needs_rehash(member.password_hash):
                members.set_password_hash(member, self._hasher.hash(password))
            members.touch_login(member, now)
            org = members.get_org(member.org_id)
            if org is None:  # FK RESTRICT makes this impossible; fail closed anyway
                raise InvalidCredentials()
            cookie = self._codec.issue(member.id, member.session_epoch)
            result = LoginResult(
                member=_member_view(member),
                org=_org_view(org),
                csrf_token=self._csrf.token_for(cookie.payload.sid),
                cookie=cookie,
            )
            uow.commit()
        return result

    def _enforce_login_limits(self, email: str, ip: str) -> None:
        """Per-IP first, then per-email (lane B note): a hit denied by the IP limit
        must not use up the email budget."""
        s = self._settings
        ip_key = self._ip_hasher.hash(ip, self._clock.now().date())
        decision = self._limiter.hit("ip", ip_key, s.rate_login_per_ip, LOGIN_WINDOW_S)
        if not decision.allowed:
            raise RateLimited(details={"scope": "ip"}, retry_after_s=decision.retry_after_s)
        decision = self._limiter.hit(
            "login", email.strip().lower(), s.rate_login_per_email, LOGIN_WINDOW_S
        )
        if not decision.allowed:
            raise RateLimited(details={"scope": "login"}, retry_after_s=decision.retry_after_s)

    # ----------------------------------------------------------------- logout

    def logout(self, principal: Principal) -> None:
        with self._uow() as uow:
            MemberRepository(uow.session).bump_session_epoch(principal.member_id)
            uow.commit()

    # --------------------------------------------------------------------- me

    def me(self, principal: Principal) -> MeResult:
        with self._uow() as uow:
            members = MemberRepository(uow.session)
            member = members.get(principal.member_id)
            org = members.get_org(principal.org_id)
            if member is None or org is None:
                raise Unauthenticated()
            return MeResult(
                member=_member_view(member),
                org=_org_view(org),
                csrf_token=self._csrf.token_for(principal.sid),
            )

    # ---------------------------------------------------------------- consent

    def accept_consent(self, principal: Principal, version: str) -> MemberView:
        current = self._settings.consent_version
        if version != current:
            raise ValidationFailed(
                details={
                    "fields": [{"path": "body.version", "problem": "version_mismatch"}]
                }
            )
        with self._uow() as uow:
            members = MemberRepository(uow.session)
            member = members.get(principal.member_id)
            if member is None:
                raise NotFound()
            if member.consented_at is None or member.consent_version != version:
                members.set_consent(member, self._clock.now(), version)
            view = _member_view(member)
            uow.commit()
        return view

    # ------------------------------------------------------------ cookie read

    def principal_from_cookie(self, cookie_value: str | None) -> Principal:
        """Verify signature and age, load the member, compare `session_epoch`.
        Any failure is `unauthenticated` (no hint which check failed)."""
        payload: CookiePayload = self._codec.parse(cookie_value or "")
        with self._uow() as uow:
            member = MemberRepository(uow.session).get(payload.member_id)
            if member is None or member.session_epoch != payload.session_epoch:
                raise Unauthenticated()
            return Principal(
                member_id=member.id,
                org_id=member.org_id,
                role=member.role,
                consented=member.consented_at is not None,
                sid=payload.sid,
            )
