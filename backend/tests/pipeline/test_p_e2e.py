"""PIPE-E2E-01..24: the whole clip pipeline, merge and check (07 section 3.15).

Real ffmpeg, mock AI, fake clock. Clips are stored as originals and the real
worker (`app.worker.build_runner`) runs until idle.
"""

from __future__ import annotations

import logging
import time

import pytest
from sqlalchemy import update

from app.ai.errors import AiPermanentError, AiTransientError
from app.ai.types import DraftFactOut, DraftOutput, EvidenceFrames, Usage
from app.errors import JobError
from app.models import Clip, FilmingSession
from tests.pipeline.pipe_support import (
    ALL_SITUATIONS,
    FnDrafter,
    ai_slots,
    csrf,
    make_short_clip,
)


def _world_session(env, situations=None):
    _, staff, vol, dog = env.world()
    return dog, vol, env.session(dog, vol, situations=situations)


def _dump(env, clip):
    return env.clip(clip.id)


# ---------------------------------------------------------------- PIPE-E2E-01


def test_pipe_e2e_01_full_pipeline_three_clips(env):
    dog, vol, sess = _world_session(env)
    clips = [
        env.add_clip(sess, "h264_5s.mp4", ordinal=1),
        env.add_clip(sess, "hevc_8s.mov", ordinal=2),
        env.add_clip(sess, "silent_5s.mp4", ordinal=3),
    ]
    steps: dict[str, list[str]] = {c.id: [] for c in clips}
    svc = env.services.clip_pipeline_service
    orig_begin = svc.begin_step

    def begin(clip_id, step, *a, **kw):
        steps[clip_id].append(step)
        return orig_begin(clip_id, step, *a, **kw)

    svc.begin_step = begin
    unmerged_at_merge: list[int] = []
    merge = env.services.merge_service
    orig_merge = merge.merge_session

    def merge_session(session_id, *a, **kw):
        unmerged_at_merge.append(len(env.facts(session_id=session_id, merged=False)))
        return orig_merge(session_id, *a, **kw)

    merge.merge_session = merge_session

    env.run()

    for c in clips:
        assert steps[c.id] == ["transcode", "transcribe", "sample", "draft"]
        assert env.clip(c.id).status == "ready"
    korean = env.transcript(clips[1].id)
    assert korean and all(t.lang == "ko" for t in korean)
    assert "간식" in korean[0].text
    assert env.transcript(clips[2].id) == []
    assert unmerged_at_merge == [unmerged_at_merge[0]] and unmerged_at_merge[0] > 0
    facts = env.facts(session_id=sess.id)
    assert facts and all(f.merged for f in facts)
    row = env.session_row(sess.id)
    assert row.status == "review" and row.review_ready_at is not None
    assert row.review_ready_at >= row.submitted_at


# ---------------------------------------------------------------- PIPE-E2E-02


def test_pipe_e2e_02_merge_waits_for_all_clips(env):
    dog, vol, sess = _world_session(env)
    env.add_clip(sess, "h264_5s.mp4", ordinal=1)
    env.add_clip(sess, "silent_5s.mp4", ordinal=2)
    third = env.add_clip(sess, "h264_5s.mp4", ordinal=3, enqueue=False)  # delayed
    env.run()
    assert env.jobs("merge") == []
    unmerged = env.facts(session_id=sess.id)
    assert unmerged and not any(f.merged for f in unmerged)
    with env.api(vol) as (client, _):
        body = client.get(f"/api/sessions/{sess.id}?include=facts").json()
    assert body.get("facts", []) == []  # I-15
    env.enqueue_step(third, "transcode")
    env.run()
    assert len(env.jobs("merge")) == 1
    assert all(f.merged for f in env.facts(session_id=sess.id))


# ---------------------------------------------------------------- PIPE-E2E-03


def test_pipe_e2e_03_ranges_valid_after_pipeline(env):
    dog, vol, sess = _world_session(env)
    bad = env.add_clip(sess, "h264_5s.mp4", ordinal=1, filename="bad_ranges.mp4")
    ok = env.add_clip(sess, "h264_5s.mp4", ordinal=2)
    env.run()
    for clip in (bad, ok):
        row = env.clip(clip.id)
        assert row.status == "ready"
    for fact in env.facts(session_id=sess.id):
        assert fact.evidence
        for ev in env.evidence(fact.id):
            clip = env.clip(ev.clip_id)
            assert clip.dog_id == dog.id and clip.status == "ready"
            assert 0 <= ev.start_s < ev.end_s <= clip.duration_s + 1e-6
            assert 1.0 - 1e-6 <= ev.end_s - ev.start_s <= 60.0 + 1e-6
            assert ev.start_s == int(ev.start_s)  # on the frame grid (k = 1)


# ---------------------------------------------------------------- PIPE-E2E-04


def test_pipe_e2e_04_situation_outside_session_is_dropped(settings, make_env):
    out = DraftOutput(
        facts=[
            DraftFactOut(
                situation="leash_walk",
                behavior="Walked on a loose leash.",
                source="clip",
                evidence=[EvidenceFrames(start_t=0, end_t=2)],
            ),
            DraftFactOut(
                situation="new_person",
                behavior="Greeted the visitor calmly.",
                source="clip",
                evidence=[EvidenceFrames(start_t=1, end_t=3)],
            ),
        ]
    )
    env = make_env(ai=ai_slots(settings, drafter=FnDrafter(lambda req: out)))
    dog, vol, sess = _world_session(env, ["leash_walk"])
    env.add_clip(sess, "h264_5s.mp4")
    env.run()
    facts = env.facts(session_id=sess.id)
    assert [f.situation for f in facts] == ["leash_walk"]


# ---------------------------------------------------------------- PIPE-E2E-05


@pytest.mark.parametrize("keep", [False, True])
def test_pipe_e2e_05_derivative_cleanup(make_env, keep):
    env = make_env(keep_originals=keep)
    dog, vol, sess = _world_session(env)
    clip = env.add_clip(sess, "h264_5s.mp4")
    env.run()
    row = env.clip(clip.id)
    assert row.status == "ready"
    keys = env.clip_keys(clip)
    names = {k.split("/clips/")[1].split("/", 1)[1] for k in keys}
    assert "playback.mp4" in names
    if keep:
        assert row.original_path is not None
        assert {"original.mp4", "audio.wav"} <= names
        assert any(n.startswith("frames/") for n in names)
    else:
        assert row.original_path is None
        assert names == {"playback.mp4"}


# ---------------------------------------------------------------- PIPE-E2E-06


def test_pipe_e2e_06_failed_clip_keeps_files(settings, make_env):
    def boom(req):
        raise JobError("ai_failed", False)

    env = make_env(ai=ai_slots(settings, drafter=FnDrafter(boom)))
    dog, vol, sess = _world_session(env)
    clip = env.add_clip(sess, "h264_5s.mp4")
    env.run()
    row = env.clip(clip.id)
    assert (row.status, row.fail_code, row.step) == ("failed", "ai_failed", "draft")
    names = {k.split("/clips/")[1].split("/", 1)[1] for k in env.clip_keys(clip)}
    assert {"original.mp4", "playback.mp4", "audio.wav"} <= names
    assert any(n.startswith("frames/") for n in names)
    assert row.original_path is not None


# ---------------------------------------------------------------- PIPE-E2E-07/08


def _failing_for(ordinals, mock):
    def fn(req):
        if req.clip_ord in ordinals:
            raise JobError("ai_failed", False)
        return mock.draft(req)[0]

    return fn


def test_pipe_e2e_07_partial_failure_still_reaches_review(settings, make_env):
    from app.ai.adapters.mock import MockAdapter

    mock = MockAdapter(settings.ai_mock_fixtures_dir)
    env = make_env(
        ai=ai_slots(settings, drafter=FnDrafter(_failing_for({2}, mock)), mock=mock)
    )
    dog, vol, sess = _world_session(env)
    c1 = env.add_clip(sess, "h264_5s.mp4", ordinal=1)
    c2 = env.add_clip(sess, "h264_5s.mp4", ordinal=2)
    c3 = env.add_clip(sess, "silent_5s.mp4", ordinal=3)
    env.run()
    assert [env.clip(c.id).status for c in (c1, c2, c3)] == ["ready", "failed", "ready"]
    assert env.session_row(sess.id).status == "review"
    assert len(env.jobs("merge")) == 1 and env.facts(session_id=sess.id)
    with env.api(vol) as (client, _):
        body = client.get(f"/api/sessions/{sess.id}?include=none").json()
    failed = [c for c in body["clips"] if c["id"] == c2.id][0]
    assert failed["error"]["retryable"] is True


def test_pipe_e2e_08_all_clips_fail_means_no_usable_clip(settings, make_env):
    def boom(req):
        raise JobError("ai_failed", False)

    env = make_env(ai=ai_slots(settings, drafter=FnDrafter(boom)))
    dog, vol, sess = _world_session(env)
    env.add_clip(sess, "h264_5s.mp4", ordinal=1)
    env.add_clip(sess, "silent_5s.mp4", ordinal=2)
    env.run()
    row = env.session_row(sess.id)
    assert (row.status, row.fail_code) == ("failed", "no_usable_clip")
    assert env.jobs("merge") == []
    with env.api(vol) as (client, token):
        r = client.post(
            f"/api/sessions/{sess.id}/retry-merge", json={}, headers=csrf(token)
        )
    assert r.status_code == 409


# ---------------------------------------------------------------- PIPE-E2E-09


def test_pipe_e2e_09_cross_clip_merge_keeps_evidence(env):
    dog, vol, sess = _world_session(env)
    a = env.add_clip(sess, "h264_5s.mp4", ordinal=1, filename="dup_pair_a.mp4")
    b = env.add_clip(sess, "len_25s.mp4", ordinal=2, filename="dup_pair_b.mp4")
    env.run()
    facts = env.facts(session_id=sess.id)
    assert len(facts) == 1 and facts[0].merged
    assert (
        facts[0].behavior == "Sat and waited until the bowl was put on the floor"
    )  # the longer text, stored without the final period (04 5 step 2)
    rows = env.evidence(facts[0].id)
    assert {r.clip_id for r in rows} == {a.id, b.id}
    assert len(rows) <= 3


# ---------------------------------------------------------------- PIPE-E2E-10


def test_pipe_e2e_10_merge_is_idempotent(env):
    dog, vol, sess = _world_session(env)
    env.add_clip(sess, "h264_5s.mp4", ordinal=1)
    env.run()
    before = [
        (f.id, f.behavior, f.flags, f.merged) for f in env.facts(session_id=sess.id)
    ]
    assert before
    report = env.services.merge_service.merge_session(sess.id)
    assert list(report.fact_ids) == []
    after = [
        (f.id, f.behavior, f.flags, f.merged) for f in env.facts(session_id=sess.id)
    ]
    assert after == before


# ---------------------------------------------------------------- PIPE-E2E-11


def _flags(fact):
    return {(f["code"], f["severity"], f["source"]) for f in fact.flags}


def _trait_session(env):
    dog, vol, sess = _world_session(env)
    env.add_clip(sess, "len_25s.mp4", ordinal=1, filename="trait_words.mp4")
    env.run()
    return {f.behavior: f for f in env.facts(session_id=sess.id)}


def test_pipe_e2e_11_rules_flags_only(env):
    by_text = _trait_session(env)
    assert len(by_text) == 5
    for text in (
        "Friendly dog that greeted the visitor",
        "Well-behaved while being brushed",
        "A calm dog that lay on the bed",
        "Doesn't mind being grabbed by the collar",
    ):
        assert ("banned_word", "warn", "rules") in _flags(by_text[text]), text
    assert by_text["Tolerates being picked up without fuss"].flags == []
    for f in by_text.values():
        for flag in f.flags:
            assert set(flag) == {"code", "severity", "source", "detail"}
    assert env.spy("checker").calls["check"] and env.ledger("check") == []
    assert env.session_row(env.facts()[0].session_id).status == "review"  # not blocked


def test_pipe_e2e_11_model_flags_paraphrase(make_env):
    env = make_env(checker="mock")
    by_text = _trait_session(env)
    flags = by_text["Tolerates being picked up without fuss"].flags
    assert [(f["code"], f["severity"], f["source"]) for f in flags] == [
        ("trait_claim", "warn", "model")
    ]
    assert "Tolerates being picked up without fuss" in flags[0]["detail"]


# ---------------------------------------------------------------- PIPE-E2E-12


@pytest.mark.parametrize(
    "error",
    [
        JobError("ai_failed", True),
        JobError("ai_failed", False),
        AiTransientError("t"),
        AiPermanentError("p"),
    ],
)
def test_pipe_e2e_12_checker_unavailable(settings, make_env, error):
    class Broken:
        def check(self, req):
            raise error

    env = make_env(ai=ai_slots(settings, checker=Broken()))
    dog, vol, sess = _world_session(env)
    env.add_clip(sess, "h264_5s.mp4")
    env.run()
    facts = env.facts(session_id=sess.id)
    assert facts
    for f in facts:
        assert ("check_unavailable", "info", "system") in _flags(f)
    row = env.session_row(sess.id)
    assert (
        row.status == "review"
        and row.review_ready_at is not None
        and row.fail_code is None
    )
    assert env.jobs("check")[0].status == "succeeded"


# ---------------------------------------------------------------- PIPE-E2E-13


def test_pipe_e2e_13_narration_injection_stays_data(env):
    dog, vol, sess = _world_session(env)
    env.add_clip(sess, "h264_5s.mp4", filename="inject_narration.mp4")
    env.run()
    req = env.spy("drafter").calls["draft"][0]
    assert any("Ignore previous instructions" in seg.text for seg in req.transcript)
    (fact,) = env.facts(session_id=sess.id)
    assert (
        fact.source == "narration"
        and fact.status == "draft"
        and fact.origin == "ai_unchanged"
    )
    assert ("banned_word", "warn", "rules") in _flags(fact)


# ---------------------------------------------------------------- PIPE-E2E-14


def test_pipe_e2e_14_ledger_rows(settings, make_env):
    from app.ai.adapters.mock import MockAdapter

    mock = MockAdapter(settings.ai_mock_fixtures_dir)
    state = {"fail": True}

    def fn(req):
        if state["fail"] and req.clip_ord == 3:
            state["fail"] = False
            raise JobError(
                "ai_failed",
                False,
                usages=[
                    Usage(provider="mock", model="mock", usd_micros=7, purpose="draft")
                ],
            )
        return mock.draft(req)[0]

    env = make_env(
        ai=ai_slots(settings, drafter=FnDrafter(fn), checker=mock, mock=mock)
    )
    dog, vol, sess = _world_session(env)
    env.add_clip(sess, "h264_5s.mp4", ordinal=1)
    env.add_clip(sess, "hevc_8s.mov", ordinal=2)
    env.add_clip(sess, "silent_5s.mp4", ordinal=3)
    env.run()
    assert len(env.ledger("transcribe")) == 2  # none for silent_5s
    assert len(env.ledger("draft")) == 3  # two ok calls and one billed failure
    assert len(env.ledger("check")) == 1  # one batch
    assert any(r.usd_micros == 7 for r in env.ledger("draft"))
    for row in env.ledger():
        assert row.dog_id == dog.id and row.session_id == sess.id
        if row.usd_micros != 7:
            assert row.usd_micros == 0


# ---------------------------------------------------------------- PIPE-E2E-15


def test_pipe_e2e_15_timing_three_30s_clips(env):
    dog, vol, sess = _world_session(env)
    for i in (1, 2, 3):
        env.add_clip(sess, "len_30s.mp4", ordinal=i)
    t0 = time.monotonic()
    env.run()
    wall = time.monotonic() - t0
    print(f"NFR-1 wall time for 3 x 30 s clips: {wall:.1f} s")
    assert wall < 300
    assert env.session_row(sess.id).status == "review"


# ---------------------------------------------------------------- PIPE-E2E-16


def test_pipe_e2e_16_api_writes_while_worker_runs(env):
    dog, vol, sess = _world_session(env)
    for i in (1, 2, 3):
        env.add_clip(sess, "len_25s.mp4", ordinal=i)
    errors: list[BaseException] = []

    def worker():
        try:
            env.run()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    import threading

    t = threading.Thread(target=worker)
    t.start()
    writes = 0
    while t.is_alive() and writes < 400:
        with env.db() as s:
            s.execute(
                update(FilmingSession)
                .where(FilmingSession.id == sess.id)
                .values(situations=ALL_SITUATIONS)
            )
            s.commit()
        writes += 1
    t.join(timeout=120)
    assert not errors and not t.is_alive()
    assert env.session_row(sess.id).status == "review"


# ---------------------------------------------------------------- PIPE-E2E-17


def test_pipe_e2e_17_unmerged_drafts_are_invisible(env):
    dog, vol, sess = _world_session(env)
    env.add_clip(sess, "h264_5s.mp4", ordinal=1)
    env.add_clip(
        sess, "h264_5s.mp4", ordinal=2, enqueue=False
    )  # keeps the merge waiting
    env.run()
    assert env.facts(session_id=sess.id, merged=False)
    with env.api(vol) as (client, _):
        body = client.get(f"/api/sessions/{sess.id}?include=facts").json()
        dog_body = client.get(f"/api/dogs/{dog.id}").json()
    assert body.get("facts", []) == []
    assert "Walked beside the handler" not in str(dog_body)


# ---------------------------------------------------------------- PIPE-E2E-18


def test_pipe_e2e_18_clip_fact_beats_narration_duplicate(env):
    dog, vol, sess = _world_session(env)
    env.add_clip(sess, "h264_5s.mp4", filename="dup_narr_clip.mp4")
    env.run()
    facts = env.facts(session_id=sess.id)
    assert [f.source for f in facts] == ["clip"]
    rows = env.evidence(facts[0].id)
    assert [(r.start_s, r.end_s) for r in rows] == [(2.0, 5.0)]  # its own evidence only


# ---------------------------------------------------------------- PIPE-E2E-19


def test_pipe_e2e_19_merged_evidence_is_capped_longest_first(env):
    dog, vol, sess = _world_session(env)
    env.add_clip(sess, "h264_5s.mp4", ordinal=1, filename="dup_five.mp4")
    env.add_clip(sess, "len_25s.mp4", ordinal=2, filename="dup_five.mp4")
    env.add_clip(sess, "len_30s.mp4", ordinal=3, filename="dup_five.mp4")
    env.run()
    facts = env.facts(session_id=sess.id)
    assert len(facts) == 1
    rows = env.evidence(facts[0].id)
    assert len(rows) == 3
    lengths = [
        r.end_s - r.start_s for r in sorted(rows, key=lambda r: -(r.end_s - r.start_s))
    ]
    assert lengths == sorted(lengths, reverse=True)
    for r in rows:
        clip = env.clip(r.clip_id)
        assert 0 <= r.start_s < r.end_s <= clip.duration_s + 1e-6
        assert 1.0 - 1e-6 <= r.end_s - r.start_s <= 60.0


# ---------------------------------------------------------------- PIPE-E2E-20


def test_pipe_e2e_20_zero_facts_clip_is_ready(env, caplog):
    dog, vol, sess = _world_session(env, ["leash_walk"])
    clip = env.add_clip(sess, "h264_5s.mp4", filename="zero_facts.mp4")
    with caplog.at_level(logging.INFO):
        env.run()
    row = env.clip(clip.id)
    assert (row.status, row.fail_code) == ("ready", None)
    assert env.facts(session_id=sess.id) == []
    assert len(env.ledger("draft")) == 1  # ledger rows kept
    assert env.session_row(sess.id).status == "review"
    assert "zero_fact_clip" in caplog.text
    with env.api(vol) as (client, _):
        body = client.get(f"/api/sessions/{sess.id}?include=facts").json()
    assert [c["status"] for c in body["clips"]] == ["ready"] and body.get(
        "facts", []
    ) == []


def test_pipe_e2e_20_empty_fact_list_is_ready_too(settings, make_env):
    env = make_env(
        ai=ai_slots(settings, drafter=FnDrafter(lambda req: DraftOutput(facts=[])))
    )
    dog, vol, sess = _world_session(env)
    clip = env.add_clip(sess, "h264_5s.mp4")
    env.run()
    assert env.clip(clip.id).status == "ready"
    assert env.session_row(sess.id).status == "review"


# ---------------------------------------------------------------- PIPE-E2E-21


def test_pipe_e2e_21_clip_under_one_second(env, tmp_path):
    dog, vol, sess = _world_session(env)
    short = make_short_clip(tmp_path / "short_0_8s.mp4", 0.8)
    clip = env.add_clip(sess, short, filename="short_0_8s.mp4")
    env.run()
    row = env.clip(clip.id)
    assert (row.status, row.fail_code) == ("ready", None)
    assert env.spy("drafter").calls["draft"] == []
    assert not any("/frames/" in k for k in env.clip_keys(clip))
    assert env.facts(session_id=sess.id) == []
    assert env.session_row(sess.id).status == "review"


# ---------------------------------------------------------------- PIPE-E2E-22


def test_pipe_e2e_22_all_clips_ready_with_zero_facts(settings, make_env):
    env = make_env(
        ai=ai_slots(
            settings, drafter=FnDrafter(lambda req: DraftOutput(facts=[])), checker=None
        ),
        checker="mock",
    )
    dog, vol, sess = _world_session(env)
    env.add_clip(sess, "h264_5s.mp4", ordinal=1)
    env.add_clip(sess, "silent_5s.mp4", ordinal=2)
    env.run()
    assert (
        env.jobs("merge")[0].status == "succeeded"
        and env.jobs("check")[0].status == "succeeded"
    )
    assert env.spy("checker").calls["check"] == []
    assert env.ledger("check") == []
    row = env.session_row(sess.id)
    assert row.status == "review" and row.review_ready_at is not None
    assert env.facts(session_id=sess.id) == []


# ---------------------------------------------------------------- PIPE-E2E-23


def test_pipe_e2e_23_review_ready_at_clear_and_set(settings, make_env):
    from app.ai.adapters.mock import MockAdapter

    mock = MockAdapter(settings.ai_mock_fixtures_dir)
    state = {"fail": True}

    def fn(req):
        if state["fail"] and req.clip_ord == 2:
            raise JobError("ai_failed", False)
        return mock.draft(req)[0]

    env = make_env(ai=ai_slots(settings, drafter=FnDrafter(fn), mock=mock))
    dog, vol, sess = _world_session(env)
    env.add_clip(sess, "h264_5s.mp4", ordinal=1)
    c2 = env.add_clip(sess, "h264_5s.mp4", ordinal=2)
    env.run()
    row = env.session_row(sess.id)
    assert row.status == "review" and row.review_ready_at is not None
    assert env.clip(c2.id).status == "failed"

    state["fail"] = False
    env.advance(60)
    with env.api(vol) as (client, token):
        r = client.post(f"/api/clips/{c2.id}/retry", json={}, headers=csrf(token))
    assert r.status_code == 200
    row = env.session_row(sess.id)
    assert (row.status, row.review_ready_at) == ("processing", None)
    first_ready = None
    while env.run_step():
        row = env.session_row(sess.id)
        assert not (row.status == "review" and row.review_ready_at is None)
        if row.status == "processing":
            assert row.review_ready_at is None
        if row.status == "review":
            first_ready = row.review_ready_at
    row = env.session_row(sess.id)
    assert (
        row.status == "review"
        and row.review_ready_at is not None
        and first_ready is not None
    )
    assert env.clip(c2.id).status == "ready"


# ---------------------------------------------------------------- PIPE-E2E-24


def test_pipe_e2e_24_check_is_one_batch_per_merge(make_env):
    env = make_env(checker="mock")
    dog, vol, sess = _world_session(env)
    env.add_clip(sess, "len_25s.mp4", ordinal=1, filename="trait_words.mp4")
    env.run()
    calls = env.spy("checker").calls["check"]
    assert len(calls) == 1 and len(calls[0].items) == 5
    assert [i.ref for i in calls[0].items] == ["C1", "C2", "C3", "C4", "C5"]
    rows = env.ledger("check")
    assert len(rows) == 1 and rows[0].session_id == sess.id and rows[0].dog_id == dog.id

    # a later clip: only the new facts are checked
    with env.db() as s:
        s.execute(
            update(FilmingSession)
            .where(FilmingSession.id == sess.id)
            .values(status="processing", review_ready_at=None)
        )
        s.commit()
    env.add_clip(sess, "h264_5s.mp4", ordinal=2)
    env.run()
    calls = env.spy("checker").calls["check"]
    assert len(calls) == 2
    new_facts = [f for f in env.facts(session_id=sess.id) if "Walked" in f.behavior]
    assert len(calls[1].items) == len(new_facts) > 0
    assert len(env.ledger("check")) == 2
