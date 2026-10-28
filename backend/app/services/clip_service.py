"""ClipService: clip status, manual retry, delete (01 sections 5.5 to 5.7, 02 6.2).

Jobs enqueued:
- retry: type = the failed step (`transcode`, `transcribe`, `sample` or `draft`),
  payload `{clip_id, session_id, dog_id}`, columns `clip_id`, `session_id`, `dog_id`,
  fresh attempts, no dedupe key.
- delete: type `purge_clip`, payload `{clip_id, dog_id}`, `dedupe_key=purge_clip:{id}`.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.clock import Clock
from app.db.uow import UnitOfWork
from app.errors import (
    ConsentRequired,
    ForbiddenRole,
    InvalidState,
    NotFound,
    NotOwnSession,
)
from app.repositories.clips import ClipRepository
from app.services.job_queue import JobQueue
from app.services.session_service import SessionService, build_clip_view
from app.services.views import ClipView, JobSpec, MediaUrls, Principal

STEP_ORDER = ("transcode", "transcribe", "sample", "draft")
RETRYABLE_CODES = frozenset({"transcode_failed", "ai_failed", "ai_invalid_output"})


@dataclass(frozen=True, slots=True)
class ClipDeleteResult:
    clip_id: str
    purge: str
    facts_deleted: int
    facts_demoted: int


class ClipService:
    def __init__(
        self,
        *,
        clock: Clock,
        job_queue: JobQueue,
        session_service: SessionService,
        media_urls: MediaUrls,
    ):
        self._clock = clock
        self._jobs = job_queue
        self._sessions = session_service
        self._media = media_urls

    # ------------------------------------------------------------ lookups

    @staticmethod
    def _load(repo: ClipRepository, who: Principal, clip_id: str):
        found = repo.scoped(clip_id, who.org_id)
        if found is None or found[2].status == "deleted":
            raise NotFound()
        return found

    @staticmethod
    def _check_owner(who: Principal, sess) -> None:
        if not who.is_staff and sess.member_id != who.member_id:
            raise NotOwnSession()

    def _view(self, repo: ClipRepository, clip) -> ClipView:
        return build_clip_view(
            clip, self._media, has_transcript=repo.has_transcript(clip.id)
        )

    # ---------------------------------------------------------------- get

    def get(self, who: Principal, clip_id: str, *, uow: UnitOfWork) -> ClipView:
        repo = ClipRepository(uow.session)
        clip, _sess, _dog = self._load(repo, who, clip_id)
        return self._view(repo, clip)

    # -------------------------------------------------------------- retry

    def retry(self, who: Principal, clip_id: str, *, uow: UnitOfWork) -> ClipView:
        if not who.consented:
            raise ConsentRequired()
        repo = ClipRepository(uow.session)
        clip, sess, dog = self._load(repo, who, clip_id)
        self._check_owner(who, sess)
        if clip.status != "failed" or clip.fail_code not in RETRYABLE_CODES:
            raise InvalidState()
        step = clip.step if clip.step in STEP_ORDER else "transcode"
        index = STEP_ORDER.index(step)
        # remove the outputs of the failed step and of every later step
        if index <= STEP_ORDER.index("transcribe"):
            repo.delete_transcript(clip.id)
        if index <= STEP_ORDER.index("sample"):
            repo.delete_segments(clip.id)
        for fact in repo.unmerged_draft_facts(clip.id):
            uow.session.delete(fact)
        if step == "transcode":
            clip.playback_path = None
        clip.status = "processing"
        clip.step = step
        clip.fail_code = None
        clip.fail_detail = None
        clip.ready_at = None
        self._sessions.reopen_for_retry(sess)
        self._jobs.enqueue(
            JobSpec(
                type=step,
                payload={"clip_id": clip.id, "session_id": sess.id, "dog_id": dog.id},
                dog_id=dog.id,
                session_id=sess.id,
                clip_id=clip.id,
            ),
            uow=uow,
        )
        uow.session.flush()
        return self._view(repo, clip)

    # ------------------------------------------------------------- delete

    def delete(
        self, who: Principal, clip_id: str, *, uow: UnitOfWork
    ) -> ClipDeleteResult:
        if not who.consented:
            raise ConsentRequired()
        repo = ClipRepository(uow.session)
        clip, sess, dog = self._load(repo, who, clip_id)
        self._check_owner(who, sess)
        if not who.is_staff and repo.confirmed_fact_cites(clip.id):
            raise ForbiddenRole()

        now = self._clock.now()
        clip.deleted_at = now
        self._jobs.cancel_for_clip(clip.id, uow=uow)

        rows = repo.evidence_of_clip(clip.id)
        repo.delete_playback([e.id for e in rows])
        facts = {ev.fact.id: ev.fact for ev in rows}
        deleted = demoted = 0
        for fact in facts.values():
            fact.evidence[:] = [e for e in fact.evidence if e.clip_id != clip.id]
            uow.session.flush()
            if not fact.merged:
                uow.session.delete(fact)
            elif not fact.evidence and fact.source in ("clip", "narration"):
                fact.status = "deleted"
                fact.deleted_at = now
                fact.deleted_by = None
                fact.confirmed_by = None
                fact.confirmed_at = None
                fact.confirmed_role = None
                deleted += 1
            elif fact.status == "confirmed":
                fact.status = "draft"
                fact.confirmed_by = None
                fact.confirmed_at = None
                fact.confirmed_role = None
                demoted += 1
        uow.session.flush()

        self._jobs.enqueue(
            JobSpec(
                type="purge_clip",
                payload={"clip_id": clip.id, "dog_id": dog.id},
                dog_id=dog.id,
                clip_id=clip.id,
                dedupe_key=f"purge_clip:{clip.id}",
            ),
            uow=uow,
        )
        self._sessions.on_clip_terminal(sess.id, uow=uow)
        return ClipDeleteResult(
            clip_id=clip.id,
            purge="queued",
            facts_deleted=deleted,
            facts_demoted=demoted,
        )
