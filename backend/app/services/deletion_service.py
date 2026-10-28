"""DeletionService, dog part (06 section 4.6; 02 section 6.1 step 1).

`request_dog_delete` hides the dog in one transaction and queues `purge_dog`. The
purge itself (`run_purge_dog`, the retention sweep, clip deletion) belongs to lane P.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.clock import Clock
from app.db.uow import UnitOfWork
from app.errors import ForbiddenRole
from app.repositories.dogs import DogRepository
from app.services.dog_service import load_dog
from app.services.job_queue import JobQueue
from app.services.views import JobSpec, Principal

PURGE_DOG_MAX_ATTEMPTS = 8


@dataclass(frozen=True, slots=True)
class PurgeTicket:
    dog_id: str
    status: str  # "deleted"
    purge: str  # "queued"


class DeletionService:
    def __init__(self, *, clock: Clock, job_queue: JobQueue):
        self._clock = clock
        self._jobs = job_queue

    def request_dog_delete(
        self, uow: UnitOfWork, principal: Principal, dog_id: str
    ) -> PurgeTicket:
        if not principal.is_staff:
            raise ForbiddenRole()
        dog = load_dog(uow, principal, dog_id)  # not_found also for an already deleted dog
        now = self._clock.now()
        dog.status = "deleted"
        dog.deleted_at = now
        dog.public_slug = None
        uow.flush()
        # Cancel first, so the purge job enqueued next is not cancelled with the rest.
        DogRepository(uow.session).cancel_queued_jobs(dog.id, now=now)
        self._jobs.enqueue(
            JobSpec(
                type="purge_dog",
                dog_id=dog.id,
                dedupe_key=f"purge_dog:{dog.id}",
                max_attempts=PURGE_DOG_MAX_ATTEMPTS,
            ),
            uow=uow,
        )
        return PurgeTicket(dog_id=dog.id, status="deleted", purge="queued")
