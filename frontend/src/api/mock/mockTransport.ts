import type {
  ApiTransport,
  TransportRequest,
  TransportResponse,
  UploadRequest,
} from "../transport";
import type {
  AddFactRequest,
  AnswerLine,
  ChecklistRequest,
  Checklist,
  Clip,
  Coverage,
  CreateDogRequest,
  CreateSessionRequest,
  Dog,
  DogDetailResponse,
  ErrorCode,
  ErrorDetails,
  Fact,
  Id,
  Member,
  PlaybackCompleteRequest,
  PublicEvidence,
  PublicFact,
  PublicProfile,
  QaAnswer,
  Session,
  SessionDetailResponse,
  Situation,
  UpdateDogRequest,
  UpdateFactRequest,
} from "../types";
import { SITUATIONS, SITUATION_LABELS, BANNER_ID } from "../../lib/constants";
import {
  IDS,
  MOCK_CAPTIONS_URL,
  MOCK_LIMITS,
  MOCK_MEDIA_URL,
  MOCK_PHOTO_URL,
  buildState,
  clipLength,
  evidence as makeEvidence,
  hex,
  type MockState,
} from "./fixtures";
import type { ScenarioName } from "./scenarios";

export interface MockTransportOptions {
  scenario?: ScenarioName;
  /** Simulated network delay per call. Default 0. */
  latencyMs?: number;
}

type Params = string[];
type Handler = (ctx: Ctx) => TransportResponse;

interface Ctx {
  req: { method: string; body: unknown; headers: Record<string, string> };
  p: Params;
  query: URLSearchParams;
  member: Member | null;
  file?: File;
}

const ok = (body: unknown, status = 200, headers: Record<string, string> = {}): TransportResponse => ({
  status,
  headers,
  body: body === undefined ? undefined : structuredClone(body),
});

class Fail extends Error {
  constructor(
    readonly status: number,
    readonly code: ErrorCode,
    readonly details: ErrorDetails = {},
    readonly headers: Record<string, string> = {},
  ) {
    super(code);
  }
}

const r = (s: string) => new RegExp(`^${s}$`);
const SEG = "([^/?]+)";
const HEALTH = /vaccin|sick|ill\b|health|\bvet\b|medic|disease|injur|bite|aggress/i;
const TOPICS: [RegExp, Situation][] = [
  [/other dog|dogs\b/i, "other_dog"],
  [/kid|child|cat\b|cats\b/i, "children_cats"],
  [/walk|leash/i, "leash_walk"],
  [/food|toy|treat/i, "food_toys"],
  [/alone|left/i, "alone_time"],
  [/stranger|visitor|people|person/i, "new_person"],
  [/handl|touch|groom/i, "handling"],
  [/rest|sleep|indoor|house/i, "indoors_rest"],
];

/**
 * In-memory ApiTransport (06 section 6.2). It enforces the error codes the
 * UI needs: unauthenticated, csrf_failed, forbidden_role, consent_required,
 * invalid_state, playback_required, flags_unacknowledged, publish checklist,
 * validation, rate_limited, qa_cost_cap_reached, not_found. It never calls
 * `fetch` or `XMLHttpRequest`.
 */
export class MockTransport implements ApiTransport {
  scenario: ScenarioName;
  readonly latencyMs: number;
  state: MockState;
  private memberId: Id | null = null;
  private routes: [string, RegExp, Handler][] = [];

  constructor(opts: MockTransportOptions = {}) {
    this.scenario = opts.scenario ?? "happy";
    this.latencyMs = opts.latencyMs ?? 0;
    this.state = buildState(this.scenario);
    this.defineRoutes();
  }

  /** Switch scenario and reset all data and the sign-in. */
  setScenario(s: ScenarioName): void {
    this.scenario = s;
    this.state = buildState(s);
    this.memberId = null;
  }

  // ------------------------------------------------------------ transport

  async request(req: TransportRequest): Promise<TransportResponse> {
    await this.delay();
    return this.dispatch(req.method, req.path, req.body, req.headers ?? {});
  }

  async upload(req: UploadRequest): Promise<TransportResponse> {
    await this.delay();
    const total = req.file.size;
    req.onProgress?.(Math.floor(total / 2), total);
    req.onProgress?.(total, total);
    return this.dispatch(req.method ?? "POST", req.path, req.fields ?? {}, req.headers ?? {}, req.file);
  }

  private async delay() {
    if (this.latencyMs > 0) await new Promise((res) => setTimeout(res, this.latencyMs));
  }

  private dispatch(
    method: string,
    path: string,
    body: unknown,
    headers: Record<string, string>,
    file?: File,
  ): TransportResponse {
    const url = new URL(path, "http://mock.local");
    const lower: Record<string, string> = {};
    for (const [k, v] of Object.entries(headers)) lower[k.toLowerCase()] = v;
    try {
      for (const [m, re, h] of this.routes) {
        if (m !== method) continue;
        const match = re.exec(url.pathname);
        if (!match) continue;
        const member = this.currentMember();
        const publicRoute = url.pathname.startsWith("/api/public/") || url.pathname === "/healthz";
        const noAuth = publicRoute || url.pathname === "/api/auth/login";
        if (!noAuth) {
          if (!member) throw new Fail(401, "unauthenticated");
          if (method !== "GET" && lower["x-csrf-token"] !== this.csrfFor(member)) {
            throw new Fail(403, "csrf_failed");
          }
        }
        return h({
          req: { method, body, headers: lower },
          p: match.slice(1),
          query: url.searchParams,
          member,
          file,
        });
      }
      throw new Fail(404, "not_found");
    } catch (e) {
      if (e instanceof Fail) {
        return {
          status: e.status,
          headers: e.headers,
          body: {
            error: { code: e.code, message: messageFor(e.code), details: e.details },
          },
        };
      }
      throw e;
    }
  }

  // --------------------------------------------------------------- helpers

  private csrfFor(m: Member) {
    return `mock-csrf-${m.id}`;
  }
  private currentMember(): Member | null {
    return this.state.members.find((m) => m.id === this.memberId) ?? null;
  }
  private id(): Id {
    return hex(this.state.nextId++);
  }
  private now(): string {
    return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  }

  private staffOnly(m: Member | null): asserts m is Member {
    if (!m || m.role !== "staff") throw new Fail(403, "forbidden_role");
  }
  private consented(m: Member | null): asserts m is Member {
    if (!m) throw new Fail(401, "unauthenticated");
    if (!m.consented_at) throw new Fail(403, "consent_required");
  }
  private dog(id: string): Dog {
    const d = this.state.dogs.find((x) => x.id === id && x.status !== "deleted");
    if (!d) throw new Fail(404, "not_found");
    return d;
  }
  private session(id: string): Session {
    const s = this.state.sessions.find((x) => x.id === id);
    if (!s) throw new Fail(404, "not_found");
    return s;
  }
  private clip(id: string): Clip {
    const c = this.state.clips.find((x) => x.id === id && !this.state.deletedClips.has(x.id));
    if (!c) throw new Fail(404, "not_found");
    return c;
  }
  private fact(id: string): Fact {
    const f = this.state.facts.find((x) => x.id === id && !this.state.deletedFacts.has(x.id));
    if (!f) throw new Fail(404, "not_found");
    return f;
  }
  private liveFacts(dogId?: Id, sessionId?: Id): Fact[] {
    return this.state.facts.filter(
      (f) =>
        !this.state.deletedFacts.has(f.id) &&
        (dogId === undefined || f.dog_id === dogId) &&
        (sessionId === undefined || f.session_id === sessionId),
    );
  }
  private liveClips(dogId?: Id, sessionId?: Id): Clip[] {
    return this.state.clips.filter((c) => {
      if (this.state.deletedClips.has(c.id)) return false;
      const s = this.session(c.session_id);
      return (dogId === undefined || s.dog_id === dogId) && (sessionId === undefined || c.session_id === sessionId);
    });
  }
  /** Fact as the signed-in member sees it (played flags, can_confirm). */
  private view(f: Fact, m: Member | null): Fact {
    const out = structuredClone(f);
    out.evidence.forEach((e) => {
      e.played_by_me = this.state.played.has(e.id);
    });
    if (f.status === "draft") {
      const allPlayed = out.evidence.every((e) => e.played_by_me);
      const blocked = this.blockedReason(f, m);
      if (blocked) {
        out.can_confirm = false;
        out.blocked_reason = blocked;
      } else if (this.scenario === "playback_required" && f.can_confirm) {
        // The client believes it may confirm; the server still checks.
        out.can_confirm = true;
        out.blocked_reason = null;
      } else {
        out.can_confirm = allPlayed;
        out.blocked_reason = allPlayed ? null : "playback_required";
      }
    }
    return out;
  }
  private blockedReason(f: Fact, m: Member | null): Fact["blocked_reason"] {
    if (!m) return "not_found";
    if (!m.consented_at) return "consent_required";
    if (f.situation === "children_cats" && m.role !== "staff") return "staff_only_situation";
    if (f.session_id === null && m.role !== "staff") return "forbidden_role";
    if (f.session_id) {
      const s = this.session(f.session_id);
      if (m.role !== "staff" && s.member_id !== m.id) return "not_own_session";
    }
    return null;
  }
  private checklist(dogId: Id): Checklist {
    const c = this.state.checklists[dogId]!;
    const confirmed = this.liveFacts(dogId).filter((f) => f.status === "confirmed").length;
    const missing: Checklist["missing"] = [];
    if (!c.people_check) missing.push("people_check");
    if (!c.known_concerns_none && !(c.known_concerns && c.known_concerns.trim())) {
      missing.push("known_concerns");
    }
    if (confirmed === 0) missing.push("confirmed_fact");
    return {
      ...c,
      confirmed_fact_count: confirmed,
      ready_to_publish: missing.length === 0,
      missing,
    };
  }
  private coverage(dogId: Id): Coverage {
    const confirmed = this.liveFacts(dogId).filter((f) => f.status === "confirmed");
    const by = SITUATIONS.map(({ code, label }) => {
      const fs = confirmed.filter((f) => f.situation === code);
      const ev = fs.flatMap((f) => f.evidence);
      const secs = Math.round(ev.reduce((s, e) => s + e.end_s - e.start_s, 0) * 10) / 10;
      return {
        situation: code,
        label,
        covered: fs.length > 0,
        clip_count: new Set(ev.map((e) => e.clip_id)).size,
        filmed_s: secs,
        confirmed_s: secs,
      };
    });
    return {
      situations_total: 8,
      situations_covered: by.filter((x) => x.covered).length,
      by_situation: by,
      not_observed: by.filter((x) => !x.covered).map((x) => ({ situation: x.situation, label: x.label })),
    };
  }
  private sessionDetail(s: Session, include: string | null): SessionDetailResponse {
    this.advance(s);
    const clips = this.liveClips(undefined, s.id);
    return {
      session: s,
      clips,
      facts: include === "none" ? [] : this.liveFacts(undefined, s.id).map((f) => this.view(f, this.currentMember())),
      progress: {
        clips_total: clips.length,
        clips_ready: clips.filter((c) => c.status === "ready").length,
        clips_failed: clips.filter((c) => c.status === "failed").length,
      },
    };
  }
  /** Each read moves processing work one step, so polling shows progress. */
  private advance(s: Session) {
    const clips = this.liveClips(undefined, s.id);
    for (const c of clips) {
      if (c.status === "uploaded") {
        c.status = "processing";
        c.step = "transcribe";
      } else if (c.status === "processing") {
        c.status = "ready";
        c.step = null;
        c.media_url = MOCK_MEDIA_URL;
        c.captions_url = MOCK_CAPTIONS_URL;
        c.ready_at = this.now();
      }
    }
    if (s.status === "processing" && clips.every((c) => c.status === "ready" || c.status === "failed")) {
      if (clips.some((c) => c.status === "ready")) {
        s.status = "review";
        s.review_ready_at = this.now();
        if (this.liveFacts(undefined, s.id).length === 0) {
          const ready = clips.find((c) => c.status === "ready")!;
          const ev = makeEvidence(this.state.nextId++, ready.id, 4, 14);
          this.state.facts.push({
            id: this.id(),
            dog_id: s.dog_id,
            session_id: s.id,
            situation: s.situations[0] ?? "handling",
            behavior: "Stood still while being touched on the back.",
            source: "clip",
            origin: "ai_unchanged",
            status: "draft",
            flags: [],
            observed_on: s.observed_on,
            evidence: [ev],
            clip_length: clipLength([ev]),
            confirmed: null,
            created_by: null,
            can_confirm: false,
            blocked_reason: "playback_required",
          });
        }
      } else {
        s.status = "failed";
        s.fail_code = "no_usable_clip";
      }
    }
  }
  private validate(ok: boolean, path: string, problem: "required" | "too_long" | "invalid_value", limit?: number) {
    if (!ok) throw new Fail(422, "validation_error", { fields: [{ path, problem, ...(limit ? { limit } : {}) }] });
  }
  private body<T>(c: Ctx): T {
    return (c.req.body ?? {}) as T;
  }

  // ----------------------------------------------------------------- routes

  private defineRoutes() {
    const add = (m: string, p: string, h: Handler) => this.routes.push([m, r(p), h]);
    const S = this.state;
    const st = () => this.state; // state is replaced by setScenario
    void S;

    add("GET", "/healthz", () => ok({ status: "ok" }));

    add("POST", "/api/auth/login", (c) => {
      const b = this.body<{ email?: string; password?: string }>(c);
      const m = st().members.find((x) => x.email === b.email && x.password === b.password);
      if (!m) throw new Fail(401, "invalid_credentials");
      this.memberId = m.id;
      return ok({ member: this.publicMember(m), org: st().org, csrf_token: this.csrfFor(m) });
    });
    add("POST", "/api/auth/logout", () => {
      this.memberId = null;
      return ok(undefined, 204);
    });
    add("GET", "/api/me", (c) =>
      ok({
        member: this.publicMember(c.member!),
        org: st().org,
        csrf_token: this.csrfFor(c.member!),
        limits: MOCK_LIMITS,
      }),
    );
    add("POST", "/api/me/consent", (c) => {
      const b = this.body<{ accepted?: boolean; version?: string }>(c);
      this.validate(b.accepted === true && !!b.version, "body.accepted", "invalid_value");
      const m = st().members.find((x) => x.id === c.member!.id)!;
      m.consented_at = this.now();
      m.consent_version = b.version!;
      return ok({ member: this.publicMember(m) });
    });

    // dogs
    add("GET", "/api/dogs", () =>
      ok({
        dogs: st()
          .dogs.filter((d) => d.status !== "deleted")
          .map((d) => {
            const facts = this.liveFacts(d.id);
            const cov = this.coverage(d.id);
            return {
              dog: d,
              coverage: { situations_total: 8, situations_covered: cov.situations_covered },
              counts: {
                draft_facts: facts.filter((f) => f.status === "draft").length,
                confirmed_facts: facts.filter((f) => f.status === "confirmed").length,
                sessions_in_review: st().sessions.filter((s) => s.dog_id === d.id && s.status === "review").length,
                clips: this.liveClips(d.id).length,
              },
            };
          }),
      }),
    );
    add("POST", "/api/dogs", (c) => {
      const b = this.body<CreateDogRequest>(c);
      this.validate(!!b.name?.trim(), "body.name", "required");
      this.validate(b.name.length <= 60, "body.name", "too_long", 60);
      const d: Dog = {
        id: this.id(),
        name: b.name.trim(),
        sex: b.sex,
        age_estimate: b.age_estimate,
        size: b.size,
        location: b.location ?? null,
        photo_url: null,
        status: "draft",
        public_slug: null,
        public_path: null,
        created_by: c.member!.id,
        created_at: this.now(),
        published_at: null,
        adopted_at: null,
      };
      st().dogs.push(d);
      st().checklists[d.id] = {
        people_check: false,
        people_check_at: null,
        known_concerns: null,
        known_concerns_none: false,
      };
      return ok({ dog: d }, 201);
    });
    add("GET", `/api/dogs/${SEG}`, (c) => {
      const d = this.dog(c.p[0]!);
      const sessions = st()
        .sessions.filter((s) => s.dog_id === d.id)
        .map((s) => ({
          ...s,
          clip_count: this.liveClips(undefined, s.id).length,
          ready_clip_count: this.liveClips(undefined, s.id).filter((x) => x.status === "ready").length,
          draft_fact_count: this.liveFacts(undefined, s.id).filter((f) => f.status === "draft").length,
        }));
      const body: DogDetailResponse = {
        dog: d,
        coverage: this.coverage(d.id),
        checklist: this.checklist(d.id),
        sessions,
        clips: this.liveClips(d.id),
        facts: this.liveFacts(d.id).map((f) => this.view(f, c.member)),
      };
      return ok(body);
    });
    add("PATCH", `/api/dogs/${SEG}`, (c) => {
      const d = this.dog(c.p[0]!);
      const b = this.body<UpdateDogRequest>(c);
      if (b.name !== undefined) {
        this.validate(!!b.name.trim(), "body.name", "required");
        d.name = b.name.trim();
      }
      if (b.sex) d.sex = b.sex;
      if (b.age_estimate !== undefined) d.age_estimate = b.age_estimate;
      if (b.size) d.size = b.size;
      if (b.location !== undefined) d.location = b.location;
      return ok({ dog: d });
    });
    add("PUT", `/api/dogs/${SEG}/photo`, (c) => {
      const d = this.dog(c.p[0]!);
      d.photo_url = MOCK_PHOTO_URL;
      return ok({ dog: d });
    });
    add("PUT", `/api/dogs/${SEG}/publish-checklist`, (c) => {
      this.staffOnly(c.member);
      const d = this.dog(c.p[0]!);
      const b = this.body<ChecklistRequest>(c);
      if (d.status === "published" && !b.people_check) throw new Fail(409, "invalid_state");
      this.validate((b.known_concerns ?? "").length <= 1000, "body.known_concerns", "too_long", 1000);
      this.validate(!(b.known_concerns_none && (b.known_concerns ?? "").trim()), "body.known_concerns_none", "invalid_value");
      const cl = st().checklists[d.id]!;
      const wasChecked = cl.people_check;
      cl.people_check = b.people_check;
      cl.people_check_at = b.people_check ? (wasChecked ? cl.people_check_at : this.now()) : null;
      cl.known_concerns = b.known_concerns?.trim() ? b.known_concerns : null;
      cl.known_concerns_none = b.known_concerns_none;
      return ok({ checklist: this.checklist(d.id) });
    });
    add("POST", `/api/dogs/${SEG}/publish`, (c) => {
      this.staffOnly(c.member);
      const d = this.dog(c.p[0]!);
      if (d.status !== "draft") throw new Fail(409, "invalid_state");
      const cl = this.checklist(d.id);
      if (!cl.ready_to_publish) throw new Fail(409, "publish_checklist_incomplete", { missing: cl.missing });
      d.status = "published";
      d.public_slug ??= `mock${d.id.slice(-8)}`;
      d.public_path = `/d/${d.public_slug}`;
      d.published_at = this.now();
      return ok({ dog: d, public_url: `https://watchme.example.org${d.public_path}` });
    });
    add("POST", `/api/dogs/${SEG}/unpublish`, (c) => {
      this.staffOnly(c.member);
      const d = this.dog(c.p[0]!);
      if (d.status !== "published" && d.status !== "adopted") throw new Fail(409, "invalid_state");
      d.status = "draft";
      d.published_at = null;
      d.adopted_at = null;
      return ok({ dog: d });
    });
    add("POST", `/api/dogs/${SEG}/adopted`, (c) => {
      this.staffOnly(c.member);
      const d = this.dog(c.p[0]!);
      if (d.status !== "draft" && d.status !== "published") throw new Fail(409, "invalid_state");
      d.status = "adopted";
      d.adopted_at = this.now();
      return ok({ dog: d });
    });
    add("DELETE", `/api/dogs/${SEG}`, (c) => {
      this.staffOnly(c.member);
      const d = this.dog(c.p[0]!);
      d.status = "deleted";
      return ok({ dog_id: d.id, status: "deleted", purge: "queued" }, 202);
    });

    // sessions
    add("POST", `/api/dogs/${SEG}/sessions`, (c) => {
      this.consented(c.member);
      const d = this.dog(c.p[0]!);
      const b = this.body<CreateSessionRequest>(c);
      this.validate(Array.isArray(b.situations) && b.situations.length > 0, "body.situations", "required");
      this.validate(b.capture_rules_ack === true, "body.capture_rules_ack", "invalid_value");
      if (d.status === "published" || d.status === "adopted") throw new Fail(409, "invalid_state");
      const s: Session = {
        id: this.id(),
        dog_id: d.id,
        member_id: c.member.id,
        owner_name: c.member.display_name,
        situations: b.situations,
        observed_on: b.observed_on ?? this.now().slice(0, 10),
        status: "open",
        fail_code: null,
        created_at: this.now(),
        submitted_at: null,
        review_ready_at: null,
      };
      st().sessions.push(s);
      return ok({ session: s }, 201);
    });
    add("GET", `/api/sessions/${SEG}`, (c) => {
      const s = this.session(c.p[0]!);
      const body = this.sessionDetail(s, c.query.get("include"));
      const etag = `W/"${hashOf(JSON.stringify(body))}"`;
      if (c.req.headers["if-none-match"] === etag) return { status: 304, headers: { etag }, body: undefined };
      return ok(body, 200, { etag });
    });
    add("POST", `/api/sessions/${SEG}/clips`, (c) => {
      this.consented(c.member);
      if (this.scenario === "rate_limited") {
        throw new Fail(429, "rate_limited", { scope: "member" }, { "retry-after": "30" });
      }
      const s = this.session(c.p[0]!);
      if (c.member.role !== "staff" && s.member_id !== c.member.id) throw new Fail(403, "not_own_session");
      if (s.status !== "open") throw new Fail(409, "invalid_state");
      const live = this.liveClips(undefined, s.id);
      if (live.length >= MOCK_LIMITS.max_clips_per_session) throw new Fail(409, "clip_limit_reached");
      const file = c.file!;
      const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
      if (!MOCK_LIMITS.allowed_extensions.includes(ext)) {
        throw new Fail(415, "unsupported_file_type", { allowed: MOCK_LIMITS.allowed_extensions });
      }
      if (file.size > MOCK_LIMITS.max_clip_bytes) {
        throw new Fail(413, "file_too_large", { max_bytes: MOCK_LIMITS.max_clip_bytes });
      }
      const fields = this.body<Record<string, string>>(c);
      const rid = fields.client_request_id;
      const key = rid ? `${s.id}:${rid}` : null;
      if (key && this.requestIds.has(key)) {
        return ok({ clip: this.clip(this.requestIds.get(key)!), warnings: [] }, 200);
      }
      const clip: Clip = {
        id: this.id(),
        session_id: s.id,
        ordinal: live.length + 1,
        original_filename: file.name,
        original_size_bytes: file.size,
        duration_s: 45,
        has_audio: true,
        status: "uploaded",
        step: "transcode",
        fail_code: null,
        error: null,
        media_url: null,
        captions_url: null,
        created_at: this.now(),
        ready_at: null,
      };
      st().clips.push(clip);
      if (key) this.requestIds.set(key, clip.id);
      return ok({ clip, warnings: [] }, 201);
    });
    add("POST", `/api/sessions/${SEG}/submit`, (c) => {
      this.consented(c.member);
      const s = this.session(c.p[0]!);
      if (s.status !== "open" || this.liveClips(undefined, s.id).length === 0) throw new Fail(409, "invalid_state");
      s.status = "processing";
      s.submitted_at = this.now();
      return ok({ session: s });
    });
    add("POST", `/api/sessions/${SEG}/retry-merge`, (c) => {
      this.consented(c.member);
      const s = this.session(c.p[0]!);
      if (s.status !== "failed" || s.fail_code !== "merge_failed") throw new Fail(409, "invalid_state");
      s.status = "processing";
      s.fail_code = null;
      s.review_ready_at = null;
      return ok({ session: s });
    });

    // clips
    add("GET", `/api/clips/${SEG}`, (c) => {
      const clip = this.clip(c.p[0]!);
      this.advance(this.session(clip.session_id));
      return ok({ clip });
    });
    add("POST", `/api/clips/${SEG}/retry`, (c) => {
      const clip = this.clip(c.p[0]!);
      if (clip.status !== "failed" || !clip.error?.retryable) throw new Fail(409, "invalid_state");
      clip.status = "processing";
      clip.step = clip.step ?? "transcribe";
      clip.fail_code = null;
      clip.error = null;
      return ok({ clip });
    });
    add("DELETE", `/api/clips/${SEG}`, (c) => {
      const clip = this.clip(c.p[0]!);
      st().deletedClips.add(clip.id);
      let deleted = 0;
      let demoted = 0;
      for (const f of this.liveFacts()) {
        if (!f.evidence.some((e) => e.clip_id === clip.id)) continue;
        if (f.status === "draft") {
          st().deletedFacts.add(f.id);
          deleted++;
        } else {
          f.evidence = f.evidence.filter((e) => e.clip_id !== clip.id);
          f.status = "draft";
          f.confirmed = null;
          f.clip_length = clipLength(f.evidence);
          if (f.evidence.length === 0) f.source = "staff_note";
          demoted++;
        }
      }
      return ok({ clip_id: clip.id, purge: "queued", facts_deleted: deleted, facts_demoted: demoted }, 202);
    });

    // facts
    add("POST", `/api/facts/${SEG}/playback-complete`, (c) => {
      const f = this.fact(c.p[0]!);
      const b = this.body<PlaybackCompleteRequest>(c);
      const ev = f.evidence.find((e) => e.id === b.evidence_id);
      if (!ev) throw new Fail(404, "not_found");
      const blocked = this.blockedReason(f, c.member);
      if (blocked === "not_own_session") throw new Fail(403, "not_own_session");
      if (f.status !== "draft") throw new Fail(409, "invalid_state");
      const len = ev.end_s - ev.start_s;
      if (!(b.position_s >= ev.end_s - 0.5 && b.watched_s >= 0.8 * len)) {
        throw new Fail(422, "validation_error", {
          fields: [{ path: "body.watched_s", problem: "range_not_completed" }],
        });
      }
      st().played.add(ev.id);
      return ok({
        fact_id: f.id,
        evidence_id: ev.id,
        completed_at: this.now(),
        all_ranges_played: f.evidence.every((e) => st().played.has(e.id)),
      });
    });
    add("POST", `/api/facts/${SEG}/confirm`, (c) => {
      this.consented(c.member);
      if (this.scenario === "rate_limited") {
        throw new Fail(429, "rate_limited", { scope: "member" }, { "retry-after": "30" });
      }
      const f = this.fact(c.p[0]!);
      if (f.status !== "draft") throw new Fail(409, "invalid_state");
      const blocked = this.blockedReason(f, c.member);
      if (blocked) throw new Fail(blocked === "consent_required" || blocked === "not_found" ? 403 : 403, blocked);
      const missing = f.evidence.filter((e) => !st().played.has(e.id)).map((e) => e.id);
      if (missing.length) throw new Fail(409, "playback_required", { missing_evidence_ids: missing });
      const ack = this.body<{ acknowledge_flags?: boolean }>(c).acknowledge_flags === true;
      if (f.flags.some((x) => x.severity === "warn") && !ack) throw new Fail(409, "flags_unacknowledged");
      const dog = this.dog(f.dog_id);
      if (dog.status === "published" && !this.checklist(dog.id).ready_to_publish) {
        throw new Fail(409, "publish_checklist_incomplete", { missing: this.checklist(dog.id).missing });
      }
      f.status = "confirmed";
      f.confirmed = {
        by_member_id: c.member.id,
        by_name: c.member.display_name,
        role: c.member.role,
        at: this.now(),
      };
      return ok({ fact: this.view(f, c.member) });
    });
    add("PATCH", `/api/facts/${SEG}`, (c) => {
      const f = this.fact(c.p[0]!);
      const blocked = this.blockedReason(f, c.member);
      if (blocked === "not_own_session") throw new Fail(403, "not_own_session");
      const b = this.body<UpdateFactRequest>(c);
      if (b.behavior !== undefined) {
        this.validate(!!b.behavior.trim(), "body.behavior", "required");
        this.validate(b.behavior.length <= 280, "body.behavior", "too_long", 280);
        f.behavior = b.behavior.trim();
      }
      if (b.situation) f.situation = b.situation;
      if (b.evidence) {
        if (b.evidence.length === 0 && f.source !== "staff_note") {
          throw new Fail(422, "validation_error", {
            fields: [{ path: "body.evidence", problem: "evidence_required" }],
          });
        }
        f.evidence = b.evidence.map((e) => {
          const keep = e.id ? f.evidence.find((x) => x.id === e.id && x.start_s === e.start_s && x.end_s === e.end_s) : undefined;
          if (keep) return keep;
          const clip = this.clip(e.clip_id);
          if (clip.status !== "ready") throw new Fail(409, "clip_not_ready");
          if (e.end_s - e.start_s < 1 || e.end_s - e.start_s > 60 || e.end_s > clip.duration_s || e.start_s < 0) {
            throw new Fail(422, "evidence_out_of_range");
          }
          return makeEvidence(this.state.nextId++, e.clip_id, e.start_s, e.end_s, clip.captions_url !== null);
        });
        f.clip_length = clipLength(f.evidence);
      }
      if (f.origin !== "human_added") f.origin = "human_edited";
      f.status = "draft";
      f.confirmed = null;
      return ok({ fact: this.view(f, c.member) });
    });
    add("DELETE", `/api/facts/${SEG}`, (c) => {
      const f = this.fact(c.p[0]!);
      st().deletedFacts.add(f.id);
      return ok(undefined, 204);
    });
    add("POST", `/api/dogs/${SEG}/facts`, (c) => {
      this.consented(c.member);
      const d = this.dog(c.p[0]!);
      const b = this.body<AddFactRequest>(c);
      this.validate(!!b.behavior?.trim(), "body.behavior", "required");
      this.validate(b.behavior.length <= 280, "body.behavior", "too_long", 280);
      const ev = (b.evidence ?? []).map((e) => {
        const clip = this.clip(e.clip_id);
        if (clip.status !== "ready") throw new Fail(409, "clip_not_ready");
        if (e.end_s - e.start_s < 1 || e.end_s - e.start_s > 60 || e.end_s > clip.duration_s) {
          throw new Fail(422, "evidence_out_of_range");
        }
        return makeEvidence(this.state.nextId++, e.clip_id, e.start_s, e.end_s, clip.captions_url !== null);
      });
      const f: Fact = {
        id: this.id(),
        dog_id: d.id,
        session_id: ev.length ? this.clip(ev[0]!.clip_id).session_id : null,
        situation: b.situation,
        behavior: b.behavior.trim(),
        source: ev.length ? "clip" : "staff_note",
        origin: "human_added",
        status: "draft",
        flags: [],
        observed_on: b.observed_on ?? this.now().slice(0, 10),
        evidence: ev,
        clip_length: clipLength(ev),
        confirmed: null,
        created_by: c.member.id,
        can_confirm: false,
        blocked_reason: null,
      };
      st().facts.push(f);
      return ok({ fact: this.view(f, c.member) }, 201);
    });

    // public
    add("GET", `/api/public/dogs/${SEG}`, (c) => ok(this.profile(c.p[0]!)));
    add("POST", `/api/public/dogs/${SEG}/ask`, (c) => {
      const b = this.body<{ question?: string }>(c);
      const q = (b.question ?? "").trim();
      if (q.length < 3) throw new Fail(422, "question_too_short");
      if (q.length > 300) throw new Fail(422, "validation_error", { fields: [{ path: "body.question", problem: "too_long", limit: 300 }] });
      const profile = this.profile(c.p[0]!);
      if (this.scenario === "rate_limited") {
        throw new Fail(429, "rate_limited", { scope: "ip" }, { "retry-after": "30" });
      }
      return ok(this.answer(profile, q));
    });

    add("GET", "/api/admin/metrics", (c) => {
      this.staffOnly(c.member);
      return ok({
        as_of: this.now(),
        draft_acceptance: { confirmed_ai_unchanged: 6, all_drafts: 10, rate: 0.6 },
        facts: { published_dogs: 1, confirmed: 5, with_clip_evidence: 5, clip_evidence_share: 1 },
        time: { median_session_to_review_s: 240, median_dog_first_session_to_publish_s: 86_400 },
        cost: { total_usd: 1.2, per_dog_usd: [{ dog_id: IDS.dogPublished, usd: 0.6 }], qa_today_usd: 0.1, qa_daily_cap_usd: 3 },
        alerts: [],
        purge_pending: [],
      });
    });
  }

  private requestIds = new Map<string, Id>();

  private publicMember(m: Member & { password?: string }): Member {
    return {
      id: m.id,
      email: m.email,
      display_name: m.display_name,
      role: m.role,
      consented_at: m.consented_at,
      consent_version: m.consent_version,
    };
  }

  private profile(slug: string): PublicProfile {
    const d = this.state.dogs.find((x) => x.public_slug === slug);
    if (!d || d.status !== "published" || this.scenario === "hidden_profile") {
      throw new Fail(404, "not_found");
    }
    const cl = this.state.checklists[d.id]!;
    const confirmed = this.liveFacts(d.id).filter((f) => f.status === "confirmed");
    const cov = this.coverage(d.id);
    const groups = SITUATIONS.map(({ code, label }) => ({
      situation: code,
      label,
      facts: confirmed.filter((f) => f.situation === code).map((f) => this.publicFact(f)),
    })).filter((g) => g.facts.length > 0);
    return {
      banner_id: BANNER_ID,
      dog: {
        slug,
        name: d.name,
        sex: d.sex,
        age_estimate: d.age_estimate,
        size: d.size,
        location: d.location,
        photo_url: d.photo_url,
        published_at: d.published_at ?? this.now(),
      },
      org: { name: this.state.org.name, country: this.state.org.country },
      coverage: {
        situations_total: 8,
        situations_covered: cov.situations_covered,
        summary: `Clips in ${cov.situations_covered} of 8 situations`,
        by_situation: cov.by_situation,
      },
      known_concerns: {
        none_known: cl.known_concerns_none,
        text: cl.known_concerns_none ? null : cl.known_concerns,
      },
      facts_by_situation: groups,
      not_observed: cov.not_observed,
      contact: this.state.org.contact,
      ask: { enabled: true, max_question_chars: 300, limit_per_hour: 10 },
    };
  }

  private publicFact(f: Fact): PublicFact {
    return {
      id: f.id,
      behavior: f.behavior,
      source: f.source,
      source_label: f.source === "staff_note" ? "Staff note" : "Seen in video",
      observed_on: f.observed_on,
      confirmed_by_label: f.confirmed ? `Confirmed by ${f.confirmed.role}` : "Confirmed by staff",
      clip_length: f.clip_length,
      notice:
        f.situation === "children_cats"
          ? { code: "ask_shelter_in_person_meeting", text: "Ask the shelter about an in-person meeting." }
          : null,
      evidence: f.evidence.map(
        (e): PublicEvidence => ({
          clip_id: e.clip_id,
          start_s: e.start_s,
          end_s: e.end_s,
          media_url: e.media_url ?? MOCK_MEDIA_URL,
          captions_url: e.captions_url,
        }),
      ),
    };
  }

  private answer(p: PublicProfile, q: string): QaAnswer {
    const limits = { remaining_this_hour: 9 };
    if (HEALTH.test(q)) {
      return {
        outcome: "health_redirect",
        heading: "Ask the shelter about health",
        hint: "Health questions are answered by the shelter, not by this page.",
        lines: [],
        cited_fact_ids: [],
        contact: p.contact,
        limits,
      };
    }
    if (this.scenario === "cost_cap") {
      throw new Fail(503, "qa_cost_cap_reached", {}, { "retry-after": "3600" });
    }
    const all = p.facts_by_situation.flatMap((g) => g.facts.map((f) => ({ g, f })));
    const wanted = new Set(TOPICS.filter(([re]) => re.test(q)).map(([, s]) => s));
    const hit = all.filter(({ g }) => wanted.has(g.situation));
    if (hit.length === 0) {
      return {
        outcome: "not_observed",
        heading: "Not seen in the clips",
        hint: "No confirmed fact covers this. Ask the shelter.",
        lines: [],
        cited_fact_ids: [],
        limits,
      };
    }
    const lines: AnswerLine[] = hit.map(({ g, f }) => ({
      fact_id: f.id,
      text: f.behavior,
      situation: g.situation,
      situation_label: SITUATION_LABELS[g.situation],
      source_label: f.source_label,
      observed_on: f.observed_on,
      confirmed_by_label: f.confirmed_by_label,
      clip_length: f.clip_length,
      notice: f.notice,
      evidence: f.evidence,
    }));
    return {
      outcome: "answered",
      heading: "What the shelter confirmed",
      lines,
      cited_fact_ids: lines.map((l) => l.fact_id),
      limits,
    };
  }
}

function hashOf(s: string): string {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = (h * 33) ^ s.charCodeAt(i);
  return (h >>> 0).toString(16);
}

const MESSAGES: Partial<Record<ErrorCode, string>> = {
  unauthenticated: "Sign in to continue.",
  invalid_credentials: "Wrong email or password.",
  csrf_failed: "The request was not accepted. Reload the page.",
  forbidden_role: "Your role cannot do this.",
  consent_required: "Accept the consent notice first.",
  not_found: "Not found.",
  invalid_state: "This action is not allowed right now.",
  playback_required: "Watch the whole clip range before you confirm this fact.",
  flags_unacknowledged: "Acknowledge the wording flags before you confirm.",
  publish_checklist_incomplete: "Finish the publish checklist first.",
  rate_limited: "Too many requests. Wait and try again.",
  qa_cost_cap_reached: "Questions are paused for today.",
  validation_error: "Check the highlighted fields.",
};
function messageFor(code: ErrorCode): string {
  return MESSAGES[code] ?? code;
}
