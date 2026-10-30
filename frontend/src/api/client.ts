import { ApiError } from "./errors";
import { HttpTransport } from "./httpTransport";
import type { ApiTransport, HttpMethod, TransportResponse } from "./transport";
import type {
  AddFactRequest,
  AskRequest,
  ChecklistRequest,
  ChecklistResponse,
  ClipResponse,
  ClipUploadResponse,
  ConfirmFactRequest,
  ConsentResponse,
  CreateDogRequest,
  CreateSessionRequest,
  DeleteClipResponse,
  DeleteDogResponse,
  DogDetailResponse,
  DogListResponse,
  DogResponse,
  ErrorCode,
  ErrorDetails,
  ErrorEnvelope,
  FactResponse,
  HealthResponse,
  Id,
  LoginResponse,
  MeResponse,
  MetricsResponse,
  PlaybackCompleteRequest,
  PlaybackCompleteResponse,
  PublicProfile,
  PublishResponse,
  QaAnswer,
  SessionDetailResponse,
  SessionSummaryResponse,
  SessionResponse,
  UpdateDogRequest,
  UpdateFactRequest,
} from "./types";

export const CSRF_HEADER = "X-CSRF-Token";

export interface ApiClientOptions {
  /** Token source (AuthProvider). Falls back to the client's own token. */
  getCsrfToken?: () => string | null;
  /** Called on every `401 unauthenticated`; AuthProvider clears state and redirects. */
  onUnauthenticated?: () => void;
}

export type SessionPoll =
  | { notModified: true; etag: string | null }
  | { notModified: false; etag: string | null; data: SessionSummaryResponse };

const UNSAFE: ReadonlySet<HttpMethod> = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function parseRetryAfter(v: string | undefined): number | null {
  if (v === undefined) return null;
  const n = Number(v);
  return Number.isFinite(n) && n >= 0 ? n : null;
}

function isEnvelope(b: unknown): b is ErrorEnvelope {
  if (typeof b !== "object" || b === null) return false;
  const e = (b as { error?: unknown }).error;
  return typeof e === "object" && e !== null && typeof (e as { code?: unknown }).code === "string";
}

/**
 * Typed methods per endpoint (01). Attaches `X-CSRF-Token` to every non-GET
 * call except login and the public `ask`, and turns error envelopes into
 * ApiError. It never builds a media URL (D7).
 */
export class ApiClient {
  private readonly transport: ApiTransport;
  private readonly opts: ApiClientOptions;
  private token: string | null = null;

  constructor(transport: ApiTransport, opts: ApiClientOptions = {}) {
    this.transport = transport;
    this.opts = opts;
  }

  get csrfToken(): string | null {
    return this.opts.getCsrfToken?.() ?? this.token;
  }
  set csrfToken(v: string | null) {
    this.token = v;
  }

  // ------------------------------------------------------------------ core

  private csrfHeaders(method: HttpMethod, csrf: boolean): Record<string, string> {
    if (!csrf || !UNSAFE.has(method)) return {};
    const t = this.csrfToken;
    return t ? { [CSRF_HEADER]: t } : {};
  }

  private async send(
    method: HttpMethod,
    path: string,
    body?: unknown,
    opts: { csrf?: boolean; headers?: Record<string, string> } = {},
  ): Promise<TransportResponse> {
    const res = await this.transport.request({
      method,
      path,
      body: body === undefined && UNSAFE.has(method) && method !== "DELETE" ? {} : body,
      headers: { ...this.csrfHeaders(method, opts.csrf ?? true), ...opts.headers },
    });
    return this.check(res);
  }

  private check(res: TransportResponse): TransportResponse {
    if (res.status >= 200 && res.status < 300) return res;
    if (res.status === 304) return res;
    let code: ErrorCode = "internal_error";
    let details: ErrorDetails = {};
    let message: string | undefined;
    if (isEnvelope(res.body)) {
      code = res.body.error.code;
      details = res.body.error.details ?? {};
      message = res.body.error.message;
    }
    if (code === "unauthenticated") {
      this.token = null;
      this.opts.onUnauthenticated?.();
    }
    throw new ApiError(
      code,
      res.status,
      details,
      parseRetryAfter(res.headers["retry-after"]),
      message,
    );
  }

  private async json<T>(
    method: HttpMethod,
    path: string,
    body?: unknown,
    opts?: { csrf?: boolean },
  ): Promise<T> {
    return (await this.send(method, path, body, opts)).body as T;
  }

  private async none(method: HttpMethod, path: string): Promise<void> {
    await this.send(method, path);
  }

  private async upload(
    path: string,
    method: "POST" | "PUT",
    field: string,
    file: File,
    extra: {
      fields?: Record<string, string>;
      onProgress?: (l: number, t: number) => void;
      signal?: AbortSignal;
    } = {},
  ): Promise<TransportResponse> {
    const res = await this.transport.upload({
      method,
      path,
      field,
      file,
      fields: extra.fields,
      headers: this.csrfHeaders(method, true),
      onProgress: extra.onProgress,
      signal: extra.signal,
    });
    return this.check(res);
  }

  // ------------------------------------------------------- auth and member

  async login(email: string, password: string): Promise<LoginResponse> {
    const r = await this.json<LoginResponse>(
      "POST",
      "/api/auth/login",
      { email, password },
      { csrf: false },
    );
    this.token = r.csrf_token;
    return r;
  }

  async logout(): Promise<void> {
    await this.none("POST", "/api/auth/logout");
    this.token = null;
  }

  async getMe(): Promise<MeResponse> {
    const r = await this.json<MeResponse>("GET", "/api/me");
    this.token = r.csrf_token;
    return r;
  }

  acceptConsent(version: string): Promise<ConsentResponse> {
    return this.json("POST", "/api/me/consent", { accepted: true, version });
  }

  // ------------------------------------------------------------------ dogs

  listDogs(): Promise<DogListResponse> {
    return this.json("GET", "/api/dogs");
  }
  createDog(body: CreateDogRequest): Promise<DogResponse> {
    return this.json("POST", "/api/dogs", body);
  }
  getDog(id: Id): Promise<DogDetailResponse> {
    return this.json("GET", `/api/dogs/${id}`);
  }
  updateDog(id: Id, body: UpdateDogRequest): Promise<DogResponse> {
    return this.json("PATCH", `/api/dogs/${id}`, body);
  }
  async uploadDogPhoto(id: Id, file: File): Promise<DogResponse> {
    return (await this.upload(`/api/dogs/${id}/photo`, "PUT", "photo", file)).body as DogResponse;
  }
  saveChecklist(id: Id, body: ChecklistRequest): Promise<ChecklistResponse> {
    return this.json("PUT", `/api/dogs/${id}/publish-checklist`, body);
  }
  publishDog(id: Id): Promise<PublishResponse> {
    return this.json("POST", `/api/dogs/${id}/publish`);
  }
  unpublishDog(id: Id): Promise<DogResponse> {
    return this.json("POST", `/api/dogs/${id}/unpublish`);
  }
  markAdopted(id: Id): Promise<DogResponse> {
    return this.json("POST", `/api/dogs/${id}/adopted`);
  }
  deleteDog(id: Id): Promise<DeleteDogResponse> {
    return this.json("DELETE", `/api/dogs/${id}`);
  }

  // -------------------------------------------------------------- sessions

  createSession(dogId: Id, body: CreateSessionRequest): Promise<SessionResponse> {
    return this.json("POST", `/api/dogs/${dogId}/sessions`, body);
  }
  getSession(id: Id, opts?: { include?: "facts" }): Promise<SessionDetailResponse>;
  getSession(id: Id, opts: { include: "none" }): Promise<SessionSummaryResponse>;
  getSession(
    id: Id,
    opts: { include?: "facts" | "none" } = {},
  ): Promise<SessionDetailResponse | SessionSummaryResponse> {
    const q = opts.include ? `?include=${opts.include}` : "";
    return this.json("GET", `/api/sessions/${id}${q}`);
  }
  /**
   * Conditional GET for the 3 s poll (If-None-Match, 304 means unchanged).
   * Sends `include=none` (01 section 5.2): the result has no `facts`
   * key, so it is typed without one. Callers that need facts read them with
   * `getSession`.
   */
  async pollSession(id: Id, etag?: string | null): Promise<SessionPoll> {
    const res = await this.send("GET", `/api/sessions/${id}?include=none`, undefined, {
      headers: etag ? { "If-None-Match": etag } : undefined,
    });
    const tag = res.headers["etag"] ?? null;
    if (res.status === 304) return { notModified: true, etag: tag ?? etag ?? null };
    return { notModified: false, etag: tag, data: res.body as SessionSummaryResponse };
  }
  submitSession(id: Id): Promise<SessionResponse> {
    return this.json("POST", `/api/sessions/${id}/submit`);
  }
  retryMerge(id: Id): Promise<SessionResponse> {
    return this.json("POST", `/api/sessions/${id}/retry-merge`);
  }

  // ----------------------------------------------------------------- clips

  async uploadClip(
    sessionId: Id,
    file: File,
    opts: {
      clientRequestId?: string;
      onProgress?: (loaded: number, total: number) => void;
      /** Cancel the upload; the promise rejects with an `AbortError`. */
      signal?: AbortSignal;
    } = {},
  ): Promise<ClipUploadResponse> {
    const res = await this.upload(`/api/sessions/${sessionId}/clips`, "POST", "file", file, {
      fields: opts.clientRequestId ? { client_request_id: opts.clientRequestId } : undefined,
      onProgress: opts.onProgress,
      signal: opts.signal,
    });
    return res.body as ClipUploadResponse;
  }
  getClip(id: Id): Promise<ClipResponse> {
    return this.json("GET", `/api/clips/${id}`);
  }
  retryClip(id: Id): Promise<ClipResponse> {
    return this.json("POST", `/api/clips/${id}/retry`);
  }
  deleteClip(id: Id): Promise<DeleteClipResponse> {
    return this.json("DELETE", `/api/clips/${id}`);
  }

  // ----------------------------------------------------------------- facts

  playbackComplete(
    factId: Id,
    report: PlaybackCompleteRequest,
  ): Promise<PlaybackCompleteResponse> {
    return this.json("POST", `/api/facts/${factId}/playback-complete`, report);
  }
  confirmFact(factId: Id, acknowledgeFlags = false): Promise<FactResponse> {
    const body: ConfirmFactRequest = acknowledgeFlags ? { acknowledge_flags: true } : {};
    return this.json("POST", `/api/facts/${factId}/confirm`, body);
  }
  updateFact(factId: Id, body: UpdateFactRequest): Promise<FactResponse> {
    return this.json("PATCH", `/api/facts/${factId}`, body);
  }
  deleteFact(factId: Id): Promise<void> {
    return this.none("DELETE", `/api/facts/${factId}`);
  }
  addFact(dogId: Id, body: AddFactRequest): Promise<FactResponse> {
    return this.json("POST", `/api/dogs/${dogId}/facts`, body);
  }

  // ---------------------------------------------------------------- public

  getPublicProfile(slug: string): Promise<PublicProfile> {
    return this.json("GET", `/api/public/dogs/${encodeURIComponent(slug)}`);
  }
  ask(slug: string, question: string): Promise<QaAnswer> {
    const body: AskRequest = { question };
    return this.json("POST", `/api/public/dogs/${encodeURIComponent(slug)}/ask`, body, {
      csrf: false,
    });
  }

  // ----------------------------------------------------------------- admin

  getMetrics(): Promise<MetricsResponse> {
    return this.json("GET", "/api/admin/metrics");
  }
  health(): Promise<HealthResponse> {
    return this.json("GET", "/healthz");
  }
}

/** Production client: `fetch` transport. Mock mode uses `createMockClient`. */
export function createHttpClient(opts: ApiClientOptions = {}): ApiClient {
  return new ApiClient(new HttpTransport(), opts);
}
