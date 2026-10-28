"""Request and response models of `/api/auth/*` and the shared `Member` / `Org` objects
(01 sections 2 and 3)."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.services.auth_service import LoginResult, MemberView, OrgView


def iso_z(value: datetime | None) -> str | None:
    """RFC 3339 UTC with `Z`, second precision (01 section 1)."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class LoginIn(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class MemberOut(BaseModel):
    id: str
    email: str
    display_name: str
    role: str
    consented_at: str | None
    consent_version: str | None

    @classmethod
    def from_view(cls, view: MemberView) -> MemberOut:
        return cls(
            id=view.id,
            email=view.email,
            display_name=view.display_name,
            role=view.role,
            consented_at=iso_z(view.consented_at),
            consent_version=view.consent_version,
        )


class ContactOut(BaseModel):
    url: str | None
    email: str | None
    phone: str | None


class OrgOut(BaseModel):
    id: str
    name: str
    country: str
    location: str
    contact: ContactOut

    @classmethod
    def from_view(cls, view: OrgView) -> OrgOut:
        return cls(
            id=view.id,
            name=view.name,
            country=view.country,
            location=view.location,
            contact=ContactOut(
                url=view.contact.url, email=view.contact.email, phone=view.contact.phone
            ),
        )


class LoginOut(BaseModel):
    member: MemberOut
    org: OrgOut
    csrf_token: str

    @classmethod
    def from_result(cls, result: LoginResult) -> LoginOut:
        return cls(
            member=MemberOut.from_view(result.member),
            org=OrgOut.from_view(result.org),
            csrf_token=result.csrf_token,
        )
