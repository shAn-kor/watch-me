"""PublishService: publish checklist, publish, unpublish, adopted (06 section 4.3;
01 sections 4.6 to 4.9; 02 section 3.1 D2 to D5).

Staff only. The role check comes first (`forbidden_role`), then the org-scoped lookup
(`not_found`, also for a `deleted` dog), then the state guards.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.clock import Clock
from app.config import Settings
from app.db.uow import UnitOfWork
from app.domain.slugs import generate_slug
from app.errors import (
    ForbiddenRole,
    InvalidState,
    PublishChecklistIncomplete,
    ValidationFailed,
)
from app.models import Dog
from app.repositories.dogs import DogRepository
from app.services.dog_service import (
    DogView,
    clean_text,
    dog_view,
    load_dog,
)
from app.services.views import MediaUrls, Principal

CONCERNS_MAX = 1000
SLUG_ATTEMPTS = 10


@dataclass(frozen=True, slots=True)
class ChecklistView:
    people_check: bool
    people_check_at: datetime | None
    known_concerns: str | None
    known_concerns_none: bool
    confirmed_fact_count: int
    ready_to_publish: bool
    missing: tuple[str, ...]  # subset of people_check, known_concerns, confirmed_fact


@dataclass(frozen=True, slots=True)
class PublishResult:
    dog: DogView
    public_url: str


def _concerns_decided(dog: Dog) -> bool:
    return bool(dog.known_concerns_none) or bool(clean_text(dog.known_concerns))


def _require_staff(principal: Principal) -> None:
    if not principal.is_staff:
        raise ForbiddenRole()


class PublishService:
    def __init__(self, *, clock: Clock, settings: Settings, media_urls: MediaUrls):
        self._clock = clock
        self._settings = settings
        self._media = media_urls

    # ------------------------------------------------------------- checklist

    def checklist_for(self, uow: UnitOfWork, dog: Dog) -> ChecklistView:
        confirmed = DogRepository(uow.session).confirmed_fact_count(dog.id)
        missing = []
        if dog.people_check_at is None:
            missing.append("people_check")
        if not _concerns_decided(dog):
            missing.append("known_concerns")
        if confirmed < 1:
            missing.append("confirmed_fact")
        return ChecklistView(
            people_check=dog.people_check_at is not None,
            people_check_at=dog.people_check_at,
            known_concerns=dog.known_concerns,
            known_concerns_none=bool(dog.known_concerns_none),
            confirmed_fact_count=confirmed,
            ready_to_publish=not missing,
            missing=tuple(missing),
        )

    def get_checklist(self, uow: UnitOfWork, principal: Principal, dog_id: str) -> ChecklistView:
        return self.checklist_for(uow, load_dog(uow, principal, dog_id))

    def set_checklist(
        self,
        uow: UnitOfWork,
        principal: Principal,
        dog_id: str,
        *,
        people_check: bool,
        known_concerns: str | None = None,
        known_concerns_none: bool = False,
    ) -> ChecklistView:
        _require_staff(principal)
        dog = load_dog(uow, principal, dog_id)
        text = clean_text(known_concerns)
        if len(text) > CONCERNS_MAX:
            raise ValidationFailed(
                details={
                    "fields": [
                        {"path": "body.known_concerns", "problem": "too_long", "limit": CONCERNS_MAX}
                    ]
                }
            )
        if known_concerns_none and text:
            raise ValidationFailed(
                details={
                    "fields": [{"path": "body.known_concerns_none", "problem": "invalid_value"}]
                }
            )
        complete = people_check and (known_concerns_none or bool(text))
        if dog.status == "published" and not complete:
            raise InvalidState("Unpublish this dog before you clear its checklist.")
        if people_check:
            if dog.people_check_at is None:
                dog.people_check_at = self._clock.now()
                dog.people_check_by = principal.member_id
        else:
            dog.people_check_at = None
            dog.people_check_by = None
        dog.known_concerns = text or None
        dog.known_concerns_none = bool(known_concerns_none)
        uow.flush()
        return self.checklist_for(uow, dog)

    # -------------------------------------------------------------- lifecycle

    def publish(self, uow: UnitOfWork, principal: Principal, dog_id: str) -> PublishResult:
        _require_staff(principal)
        dog = load_dog(uow, principal, dog_id)
        if dog.status != "draft":
            raise InvalidState("Only a draft dog can be published.")
        checklist = self.checklist_for(uow, dog)
        if not checklist.ready_to_publish:
            raise PublishChecklistIncomplete(details={"missing": list(checklist.missing)})
        if dog.public_slug is None:
            dog.public_slug = self._new_slug(uow)
        dog.status = "published"
        dog.published_at = self._clock.now()
        uow.flush()
        base = self._settings.public_base_url.rstrip("/")
        return PublishResult(dog_view(dog, self._media), f"{base}/d/{dog.public_slug}")

    def unpublish(self, uow: UnitOfWork, principal: Principal, dog_id: str) -> DogView:
        """`published` or `adopted` to `draft`. The slug and the checklist are kept."""
        _require_staff(principal)
        dog = load_dog(uow, principal, dog_id)
        if dog.status not in ("published", "adopted"):
            raise InvalidState("Only a published or adopted dog can be unpublished.")
        if dog.status == "adopted":
            dog.adopted_at = None
        dog.status = "draft"
        uow.flush()
        return dog_view(dog, self._media)

    def mark_adopted(self, uow: UnitOfWork, principal: Principal, dog_id: str) -> DogView:
        _require_staff(principal)
        dog = load_dog(uow, principal, dog_id)
        if dog.status not in ("draft", "published"):
            raise InvalidState("Only a draft or published dog can be marked adopted.")
        dog.status = "adopted"
        dog.adopted_at = self._clock.now()
        uow.flush()
        return dog_view(dog, self._media)

    def _new_slug(self, uow: UnitOfWork) -> str:
        repo = DogRepository(uow.session)
        for _ in range(SLUG_ATTEMPTS):
            slug = generate_slug()
            if not repo.slug_exists(slug):
                return slug
        raise RuntimeError("could not generate a unique public slug")
