"""`SeedBuilder`: writes rows straight into the database (07 section 2.2).

It bypasses services on purpose, so tests of one lane do not depend on another.
It fills every field the CHECK constraints in 02 require (a published dog gets a
slug and a people check; a confirmed fact gets `confirmed_at` and
`confirmed_role`). Every method commits and returns a detached row
(`expire_on_commit=False`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from argon2 import PasswordHasher
from sqlalchemy.orm import Session, sessionmaker

from app.clock import Clock
from app.db.base import new_id
from app.models import (
    Clip,
    CostLedger,
    Dog,
    Fact,
    FactEvidence,
    FilmingSession,
    Job,
    Member,
    Org,
    PlaybackEvent,
    QaLog,
    TranscriptSegment,
)

# Test constant, never a real secret. Low cost so seeding stays fast.
TEST_PASSWORD = "correct-horse-battery"
_HASHER = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
_PASSWORD_HASH = _HASHER.hash(TEST_PASSWORD)

CONSENT_VERSION = "2026-10"


@dataclass
class World:
    """The standard world of 07 section 2.2. Attributes are detached rows."""

    org_a: Org
    org_b: Org
    staff1: Member
    vol1: Member
    vol2: Member
    vol_new: Member
    staff_b: Member
    dog_empty: Dog
    dog_review: Dog
    dog_ready: Dog
    dog_pub: Dog
    dog_adopted: Dog
    dog_deleted: Dog
    dog_b: Dog
    session_review: FilmingSession
    clips_review: list[Clip] = field(default_factory=list)
    facts_review: list[Fact] = field(default_factory=list)
    facts_pub: dict[str, Fact] = field(default_factory=dict)
    clips_pub: dict[str, Clip] = field(default_factory=dict)


class SeedBuilder:
    def __init__(self, session_factory: sessionmaker[Session], clock: Clock):
        self._sf = session_factory
        self.clock = clock
        self.password = TEST_PASSWORD

    # ------------------------------------------------------------- plumbing

    def _add(self, row: Any) -> Any:
        with self._sf() as s:
            s.add(row)
            s.commit()
        return row

    # --------------------------------------------------------------- people

    def org(self, name: str = "Maple Street Rescue", **kw: Any) -> Org:
        kw.setdefault("country", "US")
        kw.setdefault("location", "Springfield")
        if not any(
            kw.get(k) for k in ("contact_url", "contact_email", "contact_phone")
        ):
            kw["contact_email"] = "contact@example.test"
        return self._add(Org(id=new_id(), name=name, **kw))

    def member(
        self,
        org: Org,
        role: str = "volunteer",
        *,
        name: str | None = None,
        email: str | None = None,
        consented: bool = True,
        **kw: Any,
    ) -> Member:
        mid = new_id()
        if consented:
            kw.setdefault("consented_at", self.clock.now())
            kw.setdefault("consent_version", CONSENT_VERSION)
        return self._add(
            Member(
                id=mid,
                org_id=org.id,
                email=email or f"{mid[:8]}@example.test",
                display_name=name or f"{role}-{mid[:4]}",
                password_hash=_PASSWORD_HASH,
                role=role,
                **kw,
            )
        )

    # ----------------------------------------------------------------- dogs

    def dog(
        self,
        org: Org,
        creator: Member,
        *,
        name: str = "Biscuit",
        status: str = "draft",
        **kw: Any,
    ) -> Dog:
        now = self.clock.now()
        kw.setdefault("age_estimate", "2 years")
        kw.setdefault("size", "medium")
        if status in ("published", "adopted"):
            kw.setdefault("known_concerns_none", True)
            kw.setdefault("people_check_at", now)
            kw.setdefault("people_check_by", creator.id)
            kw.setdefault("published_at", now)
            kw.setdefault("public_slug", f"dog{new_id()[:10]}")
        if status == "adopted":
            kw.setdefault("adopted_at", now)
        if status == "deleted":
            kw.setdefault("deleted_at", now)
        if status in ("draft",):
            kw.setdefault("people_check_at", None)
        return self._add(
            Dog(
                id=new_id(),
                org_id=org.id,
                created_by=creator.id,
                name=name,
                status=status,
                **kw,
            )
        )

    # ------------------------------------------------- sessions and clips

    def session(
        self,
        dog: Dog,
        member: Member,
        *,
        situations: list[str] | None = None,
        status: str = "open",
        **kw: Any,
    ) -> FilmingSession:
        now = self.clock.now()
        kw.setdefault("observed_on", now.date())
        kw.setdefault("rules_ack_at", now)
        if status in ("processing", "review", "failed"):
            kw.setdefault("submitted_at", now)
        if status in ("review",):
            kw.setdefault("review_ready_at", now)
        return self._add(
            FilmingSession(
                id=new_id(),
                dog_id=dog.id,
                member_id=member.id,
                situations=situations or ["leash_walk", "new_person"],
                status=status,
                **kw,
            )
        )

    def clip(
        self,
        session: FilmingSession,
        ordinal: int = 1,
        *,
        status: str = "ready",
        duration_s: float = 20.0,
        **kw: Any,
    ) -> Clip:
        cid = new_id()
        kw.setdefault("original_filename", f"clip{ordinal}.mp4")
        kw.setdefault("original_size_bytes", 1_000_000)
        kw.setdefault("has_audio", True)
        if status == "ready":
            kw.setdefault("ready_at", self.clock.now())
            kw.setdefault(
                "playback_path", f"dogs/{session.dog_id}/clips/{cid}/playback.mp4"
            )
        return self._add(
            Clip(
                id=cid,
                session_id=session.id,
                dog_id=session.dog_id,
                ordinal=ordinal,
                duration_s=duration_s,
                status=status,
                **kw,
            )
        )

    def transcript(self, clip: Clip, *texts: str) -> list[TranscriptSegment]:
        rows = [
            TranscriptSegment(
                clip_id=clip.id, idx=i, start_s=float(i), end_s=i + 1.0, text=t
            )
            for i, t in enumerate(texts)
        ]
        with self._sf() as s:
            s.add_all(rows)
            s.commit()
        return rows

    # ---------------------------------------------------------------- facts

    def fact(
        self,
        dog: Dog,
        *,
        situation: str = "leash_walk",
        behavior: str = "Walks beside the handler on a loose leash.",
        status: str = "draft",
        source: str = "clip",
        origin: str | None = None,
        session: FilmingSession | None = None,
        clip: Clip | None = None,
        ranges: list[tuple[float, float]] | None = None,
        confirmed_by: Member | None = None,
        created_by: Member | None = None,
        observed_on: date | None = None,
        **kw: Any,
    ) -> Fact:
        """Create a fact with evidence. `clip` plus `ranges` (default one 1.0-4.0 s
        range on `clip`) become `fact_evidence` rows. `status="confirmed"` fills
        the confirm triplet; a `children_cats` confirmation needs a staff member."""
        now = self.clock.now()
        if origin is None:
            origin = "human_added" if source == "staff_note" else "ai_unchanged"
        if status == "confirmed":
            who = confirmed_by or created_by
            kw.setdefault("confirmed_at", now)
            kw.setdefault(
                "confirmed_role",
                "staff"
                if situation == "children_cats"
                else (who.role if who else "staff"),
            )
            kw.setdefault("confirmed_by", who.id if who else None)
        if status == "deleted":
            kw.setdefault("deleted_at", now)
        fid = new_id()
        fact = Fact(
            id=fid,
            dog_id=dog.id,
            session_id=session.id if session else None,
            created_by=created_by.id if created_by else None,
            situation=situation,
            behavior=behavior,
            source=source,
            origin=origin,
            status=status,
            observed_on=observed_on or now.date(),
            **kw,
        )
        if clip is not None and source != "staff_note":
            for start, end in ranges or [(1.0, 4.0)]:
                fact.evidence.append(
                    FactEvidence(id=new_id(), clip_id=clip.id, start_s=start, end_s=end)
                )
        self._add(fact)
        return fact

    def playback(
        self, fact: Fact, evidence: FactEvidence, member: Member, **kw: Any
    ) -> PlaybackEvent:
        kw.setdefault("start_s", evidence.start_s)
        kw.setdefault("end_s", evidence.end_s)
        kw.setdefault("watched_s", evidence.end_s - evidence.start_s)
        return self._add(
            PlaybackEvent(
                fact_id=fact.id, evidence_id=evidence.id, member_id=member.id, **kw
            )
        )

    # ----------------------------------------------------- jobs and ledgers

    def job(self, type: str = "transcode", **kw: Any) -> Job:
        return self._add(Job(type=type, **kw))

    def qa_log(self, dog: Dog, *, outcome: str = "answered", **kw: Any) -> QaLog:
        kw.setdefault("ip_hash", "0" * 64)
        kw.setdefault("cookie_id", new_id())
        return self._add(QaLog(dog_id=dog.id, outcome=outcome, **kw))

    def ledger(
        self, purpose: str = "qa_select", *, usd_micros: int = 0, **kw: Any
    ) -> CostLedger:
        kw.setdefault("provider", "mock")
        kw.setdefault("model", "mock")
        return self._add(CostLedger(purpose=purpose, usd_micros=usd_micros, **kw))

    # ------------------------------------------------------ standard world

    def standard_world(self) -> World:
        """Org, members, dogs and facts of 07 section 2.2 (the rows the isolation,
        publish and review tests share)."""
        org_a = self.org("Maple Street Rescue")
        org_b = self.org("Other Rescue")
        staff1 = self.member(org_a, "staff", name="Staff One")
        vol1 = self.member(org_a, "volunteer", name="Vol One")
        vol2 = self.member(org_a, "volunteer", name="Vol Two")
        vol_new = self.member(org_a, "volunteer", name="Vol New", consented=False)
        staff_b = self.member(org_b, "staff", name="Staff B")

        dog_empty = self.dog(org_a, staff1, name="Empty")

        # dog_review: session by vol1 in review, 3 ready clips, 6 draft facts
        dog_review = self.dog(org_a, staff1, name="Review")
        sess = self.session(
            dog_review,
            vol1,
            status="review",
            situations=["leash_walk", "new_person", "children_cats"],
        )
        clips = [self.clip(sess, i + 1) for i in range(3)]
        facts_review: list[Fact] = []
        for i in range(6):
            situation = (
                "children_cats"
                if i == 5
                else ("leash_walk" if i % 2 == 0 else "new_person")
            )
            flags = (
                [
                    {
                        "code": "trait_claim",
                        "severity": "warn",
                        "source": "rules",
                        "detail": "Contains a trait label.",
                    }
                ]
                if i == 1
                else []
            )
            facts_review.append(
                self.fact(
                    dog_review,
                    situation=situation,
                    behavior=f"Draft behavior number {i} seen in the clip.",
                    session=sess,
                    clip=clips[i % 3],
                    created_by=None,
                    flags=flags,
                    ai_model="mock",
                )
            )

        # dog_ready: draft, checklist complete, 2 confirmed facts
        dog_ready = self.dog(
            org_a,
            staff1,
            name="Ready",
            known_concerns_none=True,
            people_check_at=self.clock.now(),
            people_check_by=staff1.id,
        )
        sess_ready = self.session(dog_ready, vol1, status="review")
        clip_ready = self.clip(sess_ready, 1)
        for sit in ("leash_walk", "new_person"):
            self.fact(
                dog_ready,
                situation=sit,
                status="confirmed",
                session=sess_ready,
                clip=clip_ready,
                confirmed_by=vol1,
            )

        # dog_pub: published, 4 confirmed facts in 3 situations + clip matrix
        dog_pub = self.dog(org_a, staff1, name="Published", status="published")
        sess_pub = self.session(
            dog_pub,
            vol1,
            status="review",
            situations=["leash_walk", "new_person", "children_cats"],
        )
        pc1 = self.clip(sess_pub, 1)
        pc2 = self.clip(sess_pub, 2)
        pc_uncited = self.clip(sess_pub, 3)
        pc_draft_only = self.clip(self.session(dog_pub, vol1, status="review"), 1)
        facts_pub = {
            "one_range": self.fact(
                dog_pub,
                status="confirmed",
                session=sess_pub,
                clip=pc1,
                confirmed_by=vol1,
                behavior="Walks on a loose leash past another dog.",
            ),
            "two_ranges": self.fact(
                dog_pub,
                situation="new_person",
                status="confirmed",
                session=sess_pub,
                clip=pc1,
                ranges=[(1.0, 3.0), (6.0, 9.0)],
                confirmed_by=vol1,
                behavior="Sniffs a new visitor, then sits.",
            ),
            "narration": self.fact(
                dog_pub,
                situation="new_person",
                status="confirmed",
                session=sess_pub,
                clip=pc2,
                source="narration",
                confirmed_by=vol1,
                behavior="The handler says the dog waits at the door.",
            ),
            "staff_note": self.fact(
                dog_pub,
                situation="leash_walk",
                status="confirmed",
                source="staff_note",
                confirmed_by=staff1,
                created_by=staff1,
                behavior="Staff note: pulls less after a week.",
            ),
            "children_cats": self.fact(
                dog_pub,
                situation="children_cats",
                status="confirmed",
                session=sess_pub,
                clip=pc2,
                confirmed_by=staff1,
                behavior="Stays calm... near a cat behind a gate.",
            ),
            "draft": self.fact(
                dog_pub,
                status="draft",
                session=sess_pub,
                clip=pc_draft_only,
                behavior="Draft only behavior, not public yet.",
            ),
            "deleted": self.fact(
                dog_pub,
                status="deleted",
                session=sess_pub,
                clip=pc1,
                behavior="A removed behavior.",
            ),
            "unmerged": self.fact(
                dog_pub,
                status="draft",
                session=sess_pub,
                clip=pc1,
                merged=False,
                behavior="Unmerged draft waiting for the session merge.",
            ),
        }

        dog_adopted = self.dog(org_a, staff1, name="Adopted", status="adopted")
        dog_deleted = self.dog(org_a, staff1, name="Deleted", status="deleted")
        dog_b = self.dog(org_b, staff_b, name="OtherOrgDog")

        return World(
            org_a=org_a,
            org_b=org_b,
            staff1=staff1,
            vol1=vol1,
            vol2=vol2,
            vol_new=vol_new,
            staff_b=staff_b,
            dog_empty=dog_empty,
            dog_review=dog_review,
            dog_ready=dog_ready,
            dog_pub=dog_pub,
            dog_adopted=dog_adopted,
            dog_deleted=dog_deleted,
            dog_b=dog_b,
            session_review=sess,
            clips_review=clips,
            facts_review=facts_review,
            facts_pub=facts_pub,
            clips_pub={
                "c1": pc1,
                "c2": pc2,
                "uncited": pc_uncited,
                "draft_only": pc_draft_only,
            },
        )
