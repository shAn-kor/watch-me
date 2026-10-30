import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClient } from "../client";
import { ApiError } from "../errors";
import { createMockClient } from "./index";
import { MOCK_ACCOUNTS, MOCK_PUBLIC_SLUG } from "./fixtures";
import { SCENARIO_NAMES } from "./scenarios";
import type { DogDetailResponse } from "../types";

afterEach(() => vi.unstubAllGlobals());

async function staff(scenario = "happy") {
  const c = createMockClient({ scenario: scenario as never });
  await c.login(MOCK_ACCOUNTS.staff.email, MOCK_ACCOUNTS.staff.password);
  return c;
}

async function firstDog(c: ApiClient): Promise<DogDetailResponse> {
  const list = await c.listDogs();
  return c.getDog(list.dogs[0]!.dog.id);
}

const code = async (p: Promise<unknown>) =>
  (await p.then(
    () => null,
    (e) => e,
  )) as ApiError | null;

describe("FE-MCK-01 mock mode never touches fetch", () => {
  it("every client method works against MockTransport", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    const xhr = vi.fn();
    vi.stubGlobal("XMLHttpRequest", xhr);

    const c = await staff();
    expect((await c.getMe()).limits.max_clips_per_session).toBe(3);
    const detail = await firstDog(c);
    expect(detail.coverage.by_situation).toHaveLength(8);
    const dogId = detail.dog.id;

    const created = await c.createDog({
      name: "Pip",
      sex: "female",
      age_estimate: "1y",
      size: "small",
    });
    await c.updateDog(created.dog.id, { name: "Pippa" });
    await c.uploadDogPhoto(created.dog.id, new File(["x"], "p.jpg"));
    await c.saveChecklist(dogId, {
      people_check: true,
      known_concerns: null,
      known_concerns_none: true,
    });

    const session = await c.createSession(created.dog.id, {
      situations: ["handling"],
      capture_rules_ack: true,
    });
    const progress = vi.fn();
    const up = await c.uploadClip(
      session.session.id,
      new File(["x"], "a.mp4", { type: "video/mp4" }),
      { onProgress: progress },
    );
    expect(up.clip.session_id).toBe(session.session.id);
    expect(progress).toHaveBeenCalled();
    await c.getClip(up.clip.id);
    await c.getSession(session.session.id);
    expect((await c.pollSession(session.session.id)).notModified).toBe(false);
    await c.submitSession(session.session.id);

    const fact = detail.facts.find((f) => f.status === "draft" && f.evidence.length)!;
    for (const ev of fact.evidence) {
      await c.playbackComplete(fact.id, {
        evidence_id: ev.id,
        position_s: ev.end_s,
        watched_s: ev.end_s - ev.start_s,
      });
    }
    const confirmed = await c.confirmFact(fact.id, true);
    expect(confirmed.fact.status).toBe("confirmed");
    await c.updateFact(fact.id, { behavior: "Sat calmly." });
    const added = await c.addFact(dogId, { situation: "handling", behavior: "Sat." });
    expect(added.fact.source).toBe("staff_note");
    await c.deleteFact(added.fact.id);

    const pub = await c.publishDog(dogId);
    expect(pub.public_url).toContain("/d/");
    await c.unpublishDog(dogId);
    await c.markAdopted(dogId);
    await c.deleteDog(created.dog.id);
    await c.getMetrics();
    await c.health();

    const profile = await c.getPublicProfile(MOCK_PUBLIC_SLUG);
    expect(profile.banner_id).toBe("pub0_v1");
    expect(profile.dog.slug).toBe(MOCK_PUBLIC_SLUG);
    const ans = await c.ask(MOCK_PUBLIC_SLUG, "Does he like other dogs?");
    expect(["answered", "not_observed", "health_redirect"]).toContain(ans.outcome);
    const health = await c.ask(MOCK_PUBLIC_SLUG, "Is he vaccinated?");
    expect(health.outcome).toBe("health_redirect");

    await c.logout();
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(xhr).not.toHaveBeenCalled();
  });

  it("the mock enforces auth, CSRF and consent", async () => {
    const c = createMockClient();
    expect((await code(c.getMe()))?.code).toBe("unauthenticated");
    expect((await code(c.login("x@y.z", "nope")))?.code).toBe("invalid_credentials");

    await c.login(MOCK_ACCOUNTS.volunteer.email, MOCK_ACCOUNTS.volunteer.password);
    const dogId = (await c.listDogs()).dogs[0]!.dog.id;
    const body = { situations: ["handling" as const], capture_rules_ack: true };
    expect((await code(c.createSession(dogId, body)))?.code).toBe("consent_required");
    await c.acceptConsent("2026-10-28");
    await c.createSession(dogId, body);

    c.csrfToken = "wrong";
    const e = await code(c.createSession(dogId, body));
    expect(e?.code).toBe("csrf_failed");
    expect(e?.status).toBe(403);
  });

  it("a volunteer cannot publish", async () => {
    const c = createMockClient();
    await c.login(MOCK_ACCOUNTS.volunteer.email, MOCK_ACCOUNTS.volunteer.password);
    const dogId = (await c.listDogs()).dogs[0]!.dog.id;
    expect((await code(c.publishDog(dogId)))?.code).toBe("forbidden_role");
  });
});

describe("FE-MCK-02 mock scenarios", () => {
  it("lists the named scenarios", () => {
    expect(SCENARIO_NAMES).toEqual(
      expect.arrayContaining([
        "happy",
        "failed_clip",
        "merge_failed",
        "zero_fact_clip",
        "rate_limited",
        "cost_cap",
        "hidden_profile",
        "playback_required",
      ]),
    );
  });

  it("failed clip", async () => {
    const c = await staff("failed_clip");
    const d = await firstDog(c);
    const failed = d.clips.find((x) => x.status === "failed");
    expect(failed).toBeDefined();
    expect(failed!.fail_code).not.toBeNull();
    expect(failed!.error).toMatchObject({ retryable: true });
    const r = await c.retryClip(failed!.id);
    expect(r.clip.status).toBe("processing");
  });

  it("merge failed, then retry merge", async () => {
    const c = await staff("merge_failed");
    const d = await firstDog(c);
    const s = d.sessions.find((x) => x.fail_code === "merge_failed")!;
    expect(s.status).toBe("failed");
    const r = await c.retryMerge(s.id);
    expect(r.session.status).toBe("processing");
    expect(r.session.fail_code).toBeNull();
  });

  it("zero-fact clip", async () => {
    const c = await staff("zero_fact_clip");
    const d = await firstDog(c);
    const cited = new Set(d.facts.flatMap((f) => f.evidence.map((e) => e.clip_id)));
    const orphan = d.clips.find((x) => x.status === "ready" && !cited.has(x.id));
    expect(orphan).toBeDefined();
  });

  it("429 with Retry-After", async () => {
    const c = createMockClient({ scenario: "rate_limited" });
    const e = await code(c.ask(MOCK_PUBLIC_SLUG, "Is he good with kids?"));
    expect(e?.code).toBe("rate_limited");
    expect(e?.status).toBe(429);
    expect(e?.retryAfter).toBeGreaterThan(0);
  });

  it("cost cap", async () => {
    const c = createMockClient({ scenario: "cost_cap" });
    const e = await code(c.ask(MOCK_PUBLIC_SLUG, "Is he good with kids?"));
    expect(e?.code).toBe("qa_cost_cap_reached");
    expect(e?.status).toBe(503);
  });

  it("hidden profile", async () => {
    const c = createMockClient({ scenario: "hidden_profile" });
    const e = await code(c.getPublicProfile(MOCK_PUBLIC_SLUG));
    expect(e?.code).toBe("not_found");
    expect(e?.status).toBe(404);
  });

  it("playback required until every range is played", async () => {
    const c = await staff("playback_required");
    const d = await firstDog(c);
    const fact = d.facts.find((f) => f.status === "draft" && f.evidence.length >= 1)!;
    const e = await code(c.confirmFact(fact.id));
    expect(e?.code).toBe("playback_required");
    expect(e?.details.missing_evidence_ids).toEqual(fact.evidence.map((x) => x.id));
    let last;
    for (const ev of fact.evidence) {
      last = await c.playbackComplete(fact.id, {
        evidence_id: ev.id,
        position_s: ev.end_s,
        watched_s: ev.end_s - ev.start_s,
      });
    }
    expect(last!.all_ranges_played).toBe(true);
    expect((await c.confirmFact(fact.id, true)).fact.status).toBe("confirmed");
  });

  it("playback numbers below the threshold are rejected (API 5.8)", async () => {
    const c = await staff("playback_required");
    const d = await firstDog(c);
    const fact = d.facts.find((f) => f.status === "draft" && f.evidence.length >= 1)!;
    const ev = fact.evidence[0]!;
    const e = await code(
      c.playbackComplete(fact.id, { evidence_id: ev.id, position_s: ev.start_s, watched_s: 0 }),
    );
    expect(e?.code).toBe("validation_error");
    expect(e?.details.fields?.[0]?.problem).toBe("range_not_completed");
  });
});

describe("session detail include and public location (contract drift)", () => {
  it("include=none has no facts key; the default read has facts", async () => {
    const c = await staff();
    const dog = await firstDog(c);
    const s = dog.sessions[0]!;
    const light = await c.getSession(s.id, { include: "none" });
    expect("facts" in light).toBe(false);
    const polled = await c.pollSession(s.id);
    expect(polled.notModified).toBe(false);
    if (!polled.notModified) expect("facts" in polled.data).toBe(false);
    expect(Array.isArray((await c.getSession(s.id)).facts)).toBe(true);
  });

  it("public location is a non-empty string even when the dog has none", async () => {
    const c = createMockClient({ scenario: "happy" });
    const p = await c.getPublicProfile(MOCK_PUBLIC_SLUG);
    expect(typeof p.dog.location).toBe("string");
    expect(p.dog.location.length).toBeGreaterThan(0);
  });
});
