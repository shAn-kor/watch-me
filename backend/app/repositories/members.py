"""Member and org reads and writes for the auth service (all SQL lives here)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import Member, Org


class MemberRepository:
    def __init__(self, session: Session):
        self._s = session

    def get(self, member_id: str) -> Member | None:
        return self._s.get(Member, member_id)

    def get_by_email(self, email: str) -> Member | None:
        """Case-insensitive lookup (the unique index is on the stored spelling)."""
        return self._s.scalar(
            select(Member).where(func.lower(Member.email) == email.strip().lower())
        )

    def get_org(self, org_id: str) -> Org | None:
        return self._s.get(Org, org_id)

    def touch_login(self, member: Member, now: datetime) -> None:
        member.last_login_at = now

    def set_password_hash(self, member: Member, password_hash: str) -> None:
        member.password_hash = password_hash

    def set_consent(self, member: Member, at: datetime, version: str) -> None:
        member.consented_at = at
        member.consent_version = version

    def bump_session_epoch(self, member_id: str) -> None:
        """Revoke every cookie issued so far (logout). Atomic in SQL."""
        self._s.execute(
            update(Member)
            .where(Member.id == member_id)
            .values(session_epoch=Member.session_epoch + 1)
        )
