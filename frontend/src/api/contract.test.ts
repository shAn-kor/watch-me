import type { paths } from "./generated/openapi";
import type * as T from "./types";

/**
 * FE-API-05 contract drift. `generated/openapi.d.ts` comes from the backend's
 * OpenAPI JSON (`pnpm contract`). Each line below says "the hand-written type
 * in types.ts and the schema the backend publishes accept the same values".
 * A drift turns a `true` into an error, so `tsc --noEmit` (pnpm build,
 * pnpm typecheck) fails. Vitest only checks that the file loads.
 */

/** Every string literal becomes `string`: the backend types many enums as `str`. */
type Widen<T> = T extends string
  ? string
  : T extends readonly (infer U)[]
    ? Widen<U>[]
    : T extends object
      ? { [K in keyof T]: Widen<T[K]> }
      : T;
type Eq<A, B> = [A] extends [B] ? ([B] extends [A] ? true : false) : false;
/**
 * `H` is the hand-written type, `G` the generated one. Same keys, optionality,
 * nullability and nesting (enums widened), and every `H` value is a valid `G`
 * value (so a backend `Literal` that lacks one of our values fails).
 */
type Same<H, G> = Eq<Widen<H>, Widen<G>> extends true
  ? [H] extends [G]
    ? true
    : false
  : false;
type Json<R> = R extends { content: { "application/json": infer B } } ? B : never;
type Ok<Op> = Op extends { responses: infer R }
  ? R extends { 200: infer S }
    ? Json<S>
    : R extends { 201: infer S }
      ? Json<S>
      : R extends { 202: infer S }
        ? Json<S>
        : never
  : never;
type Body<Op> = Op extends { requestBody?: { content: { "application/json": infer B } } }
  ? B
  : never;

type Get<P extends keyof paths, M extends keyof paths[P]> = paths[P][M];

/** Requests: everything the client can build must be accepted by the backend. */
type Sends<H, G> = [H] extends [G] ? true : false;

/** Compile-time only: assigning `false` to a `true` slot is an error. */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
function ok<_T extends true>(): void {}

describe("FE-API-05 contract drift (checked by tsc)", () => {
  it("response bodies match types.ts", () => {
    ok<Same<T.LoginResponse, Ok<Get<"/api/auth/login", "post">>>>();
    ok<Same<T.MeResponse, Ok<Get<"/api/me", "get">>>>();
    ok<Same<T.ConsentResponse, Ok<Get<"/api/me/consent", "post">>>>();
    ok<Same<T.DogListResponse, Ok<Get<"/api/dogs", "get">>>>();
    ok<Same<T.DogResponse, Ok<Get<"/api/dogs", "post">>>>();
    ok<Same<T.DogDetailResponse, Ok<Get<"/api/dogs/{dog_id}", "get">>>>();
    ok<Same<T.ChecklistResponse, Ok<Get<"/api/dogs/{dog_id}/publish-checklist", "put">>>>();
    ok<Same<T.PublishResponse, Ok<Get<"/api/dogs/{dog_id}/publish", "post">>>>();
    ok<Same<T.DeleteDogResponse, Ok<Get<"/api/dogs/{dog_id}", "delete">>>>();
    ok<Same<T.SessionResponse, Ok<Get<"/api/dogs/{dog_id}/sessions", "post">>>>();
    ok<Same<T.ClipUploadResponse, Ok<Get<"/api/sessions/{session_id}/clips", "post">>>>();
    ok<Same<T.ClipResponse, Ok<Get<"/api/clips/{clip_id}", "get">>>>();
    ok<Same<T.DeleteClipResponse, Ok<Get<"/api/clips/{clip_id}", "delete">>>>();
    ok<Same<T.PlaybackCompleteResponse, Ok<Get<"/api/facts/{fact_id}/playback-complete", "post">>>>();
    ok<Same<T.FactResponse, Ok<Get<"/api/facts/{fact_id}", "patch">>>>();
    ok<Same<T.MetricsResponse, Ok<Get<"/api/admin/metrics", "get">>>>();
    ok<Same<T.HealthResponse, Ok<Get<"/healthz", "get">>>>();
    ok<Same<T.PublicProfile, Ok<Get<"/api/public/dogs/{slug}", "get">>>>();
    ok<Same<T.QaAnswer, Ok<Get<"/api/public/dogs/{slug}/ask", "post">>>>();
    ok<Same<T.SessionDetailResponse, Ok<Get<"/api/sessions/{session_id}", "get">>>>();
    expect(true).toBe(true);
  });

  it("request bodies match types.ts", () => {
    ok<Sends<T.LoginRequest, Body<Get<"/api/auth/login", "post">>>>();
    ok<Sends<T.ConsentRequest, Body<Get<"/api/me/consent", "post">>>>();
    ok<Sends<T.CreateDogRequest, Body<Get<"/api/dogs", "post">>>>();
    ok<Sends<T.UpdateDogRequest, Body<Get<"/api/dogs/{dog_id}", "patch">>>>();
    ok<Sends<T.ChecklistRequest, Body<Get<"/api/dogs/{dog_id}/publish-checklist", "put">>>>();
    ok<Sends<T.CreateSessionRequest, Body<Get<"/api/dogs/{dog_id}/sessions", "post">>>>();
    ok<Sends<T.PlaybackCompleteRequest, Body<Get<"/api/facts/{fact_id}/playback-complete", "post">>>>();
    ok<Sends<T.UpdateFactRequest, Body<Get<"/api/facts/{fact_id}", "patch">>>>();
    ok<Sends<T.AddFactRequest, Body<Get<"/api/dogs/{dog_id}/facts", "post">>>>();
    ok<Sends<T.AskRequest, Body<Get<"/api/public/dogs/{slug}/ask", "post">>>>();
    expect(true).toBe(true);
  });
});
