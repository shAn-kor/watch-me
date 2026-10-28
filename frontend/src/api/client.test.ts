import { describe, expect, it, vi } from "vitest";
import { ApiClient } from "./client";
import { ApiError } from "./errors";
import type {
  ApiTransport,
  TransportRequest,
  TransportResponse,
  UploadRequest,
} from "./transport";
import type { ErrorCode } from "./types";

class FakeTransport implements ApiTransport {
  requests: TransportRequest[] = [];
  uploads: UploadRequest[] = [];
  next: TransportResponse = { status: 200, headers: {}, body: {} };
  async request(req: TransportRequest) {
    this.requests.push(req);
    return this.next;
  }
  async upload(req: UploadRequest) {
    this.uploads.push(req);
    return this.next;
  }
  get last(): TransportRequest {
    const r = this.requests[this.requests.length - 1];
    if (!r) throw new Error("no request");
    return r;
  }
}

const envelope = (code: ErrorCode, details = {}) => ({
  error: { code, message: "msg", details },
});

describe("FE-API ApiClient", () => {
  it("FE-API-01 CSRF header on unsafe calls only", async () => {
    const t = new FakeTransport();
    const c = new ApiClient(t, { getCsrfToken: () => "tok-1" });
    const header = () => t.last.headers?.["X-CSRF-Token"];

    await c.createDog({
      name: "Rex",
      sex: "male",
      age_estimate: "2y",
      size: "medium",
    });
    expect(t.last.method).toBe("POST");
    expect(header()).toBe("tok-1");

    await c.updateDog("d1", { name: "Rexy" });
    expect(t.last.method).toBe("PATCH");
    expect(header()).toBe("tok-1");

    await c.saveChecklist("d1", {
      people_check: true,
      known_concerns: null,
      known_concerns_none: true,
    });
    expect(t.last.method).toBe("PUT");
    expect(header()).toBe("tok-1");

    t.next = { status: 204, headers: {}, body: undefined };
    await c.deleteFact("f1");
    expect(t.last.method).toBe("DELETE");
    expect(header()).toBe("tok-1");

    await c.getDog("d1");
    expect(t.last.method).toBe("GET");
    expect(header()).toBeUndefined();

    t.next = { status: 200, headers: {}, body: { csrf_token: "x" } };
    await c.login("a@b.c", "pw");
    expect(t.last.method).toBe("POST");
    expect(header()).toBeUndefined();

    await c.ask("slug", "Does he like dogs?");
    expect(t.last.method).toBe("POST");
    expect(header()).toBeUndefined();
  });

  it("FE-API-01 uploads carry the CSRF header too", async () => {
    const t = new FakeTransport();
    const c = new ApiClient(t, { getCsrfToken: () => "tok-1" });
    const file = new File(["x"], "a.mp4", { type: "video/mp4" });
    await c.uploadClip("s1", file, { clientRequestId: "r1" });
    expect(t.uploads[0]!.headers?.["X-CSRF-Token"]).toBe("tok-1");
    expect(t.uploads[0]!.field).toBe("file");
    expect(t.uploads[0]!.fields).toEqual({ client_request_id: "r1" });
    await c.uploadDogPhoto("d1", file);
    expect(t.uploads[1]!.field).toBe("photo");
    expect(t.uploads[1]!.method).toBe("PUT");
  });

  it("FE-API-01 JSON bodies are sent for body-less POSTs", async () => {
    const t = new FakeTransport();
    const c = new ApiClient(t, { getCsrfToken: () => "t" });
    await c.submitSession("s1");
    expect(t.last.body).toEqual({});
  });

  it("FE-API-02 error envelope becomes ApiError", async () => {
    const t = new FakeTransport();
    const c = new ApiClient(t);
    const cases: [number, ErrorCode, Record<string, unknown>][] = [
      [409, "playback_required", { missing_evidence_ids: ["e1"] }],
      [422, "validation_error", { fields: [{ path: "body.name", problem: "required" }] }],
      [413, "file_too_large", { max_bytes: 209715200 }],
      [409, "publish_checklist_incomplete", { missing: ["people_check"] }],
      [500, "internal_error", { request_id: "r-1" }],
    ];
    for (const [status, code, details] of cases) {
      t.next = { status, headers: {}, body: envelope(code, details) };
      const err = await c.getDog("d1").catch((e) => e);
      expect(err).toBeInstanceOf(ApiError);
      expect(err.code).toBe(code);
      expect(err.status).toBe(status);
      expect(err.details).toEqual(details);
      expect(err.retryAfter).toBeNull();
    }
  });

  it("FE-API-02 Retry-After is parsed into seconds", async () => {
    const t = new FakeTransport();
    const c = new ApiClient(t);
    t.next = {
      status: 429,
      headers: { "retry-after": "42" },
      body: envelope("rate_limited", { scope: "ip" }),
    };
    const err = await c.ask("s", "question?").catch((e) => e);
    expect(err.code).toBe("rate_limited");
    expect(err.retryAfter).toBe(42);
    expect(err.details.scope).toBe("ip");
  });

  it("FE-API-02 a non-envelope error body still raises ApiError", async () => {
    const t = new FakeTransport();
    const c = new ApiClient(t);
    t.next = { status: 502, headers: {}, body: undefined };
    const err = await c.getMe().catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(502);
    expect(err.code).toBe("internal_error");
  });

  it("FE-API-03 unauthenticated clears auth and notifies", async () => {
    const t = new FakeTransport();
    const onUnauthenticated = vi.fn();
    const c = new ApiClient(t, { onUnauthenticated });
    c.csrfToken = "old";
    t.next = { status: 401, headers: {}, body: envelope("unauthenticated") };
    await expect(c.listDogs()).rejects.toMatchObject({ code: "unauthenticated" });
    expect(onUnauthenticated).toHaveBeenCalledTimes(1);
    expect(c.csrfToken).toBeNull();
  });

  it("FE-API-03 invalid_credentials does not trigger the redirect", async () => {
    const t = new FakeTransport();
    const onUnauthenticated = vi.fn();
    const c = new ApiClient(t, { onUnauthenticated });
    t.next = { status: 401, headers: {}, body: envelope("invalid_credentials") };
    await expect(c.login("a@b.c", "bad")).rejects.toMatchObject({
      code: "invalid_credentials",
    });
    expect(onUnauthenticated).not.toHaveBeenCalled();
  });

  it("FE-API-04 getMe restores the member and the CSRF token", async () => {
    const t = new FakeTransport();
    const c = new ApiClient(t); // fresh page load: no token
    expect(c.csrfToken).toBeNull();
    t.next = {
      status: 200,
      headers: {},
      body: { member: { id: "m1" }, org: { id: "o1" }, csrf_token: "tok-9", limits: {} },
    };
    const me = await c.getMe();
    expect(me.member.id).toBe("m1");
    expect(c.csrfToken).toBe("tok-9");
    await c.createSession("d1", { situations: ["handling"], capture_rules_ack: true });
    expect(t.last.headers?.["X-CSRF-Token"]).toBe("tok-9");
  });

  it("FE-API-05 contract drift needs the backend OpenAPI of the same commit", () => {
    // Runs in integration (08 section 10 item 5): regenerate types.ts from
    // backend openapi.json, diff, tsc --noEmit. Not runnable inside lane F.
  });

  it("paths and methods follow the API spec", async () => {
    const t = new FakeTransport();
    const c = new ApiClient(t, { getCsrfToken: () => "t" });
    t.next = { status: 200, headers: {}, body: {} };
    await c.getSession("s1");
    expect(t.last).toMatchObject({ method: "GET", path: "/api/sessions/s1" });
    await c.getSession("s1", { include: "none" });
    expect(t.last.path).toBe("/api/sessions/s1?include=none");
    await c.playbackComplete("f1", { evidence_id: "e1", position_s: 21, watched_s: 9 });
    expect(t.last).toMatchObject({
      method: "POST",
      path: "/api/facts/f1/playback-complete",
      body: { evidence_id: "e1", position_s: 21, watched_s: 9 },
    });
    await c.confirmFact("f1", true);
    expect(t.last.body).toEqual({ acknowledge_flags: true });
    await c.getPublicProfile("k7m2");
    expect(t.last.path).toBe("/api/public/dogs/k7m2");
    await c.retryMerge("s1");
    expect(t.last.path).toBe("/api/sessions/s1/retry-merge");
  });

  it("pollSession sends If-None-Match and reports 304", async () => {
    const t = new FakeTransport();
    const c = new ApiClient(t);
    t.next = { status: 304, headers: { etag: 'W/"a"' }, body: undefined };
    const r = await c.pollSession("s1", 'W/"a"');
    expect(t.last.headers?.["If-None-Match"]).toBe('W/"a"');
    expect(r).toEqual({ notModified: true, etag: 'W/"a"' });
    t.next = { status: 200, headers: { etag: 'W/"b"' }, body: { session: { id: "s1" } } };
    const r2 = await c.pollSession("s1", 'W/"a"');
    expect(r2.notModified).toBe(false);
    expect(r2.etag).toBe('W/"b"');
  });
});
