import { render, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { vi } from "vitest";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ApiClient } from "../../api/client";
import { createMockClient, MOCK_ACCOUNTS, MOCK_IDS } from "../../api/mock";
import type { ScenarioName } from "../../api/mock";
import { ApiProvider } from "../../api/provider";
import type {
  DogDetailResponse,
  MeResponse,
  SessionDetailResponse,
  SessionSummaryResponse,
} from "../../api/types";
import { App, createQueryClient } from "../../app/App";
import { createTestRouter } from "../../app/router";
import { CreatorProviders } from "../../components/creator/CreatorProviders";
import { installFakeVideo, fakeVideo } from "../../components/testing/fakeVideo";

export { MOCK_IDS };
export const CONSENT_VERSION = "2026-10-28";

export type Who = "staff" | "volunteer" | null;

export interface RenderOpts {
  /** Signed-in account before the first render; null/absent = signed out. */
  as?: Who;
  /** Accept the consent notice for the signed-in account (volunteer starts without). */
  consented?: boolean;
  scenario?: ScenarioName;
  client?: ApiClient;
  /** userEvent options (fake-timer tests pass `advanceTimers`). */
  user?: Parameters<typeof userEvent.setup>[0];
}

export async function prepareClient(opts: RenderOpts = {}): Promise<ApiClient> {
  const client = opts.client ?? createMockClient({ scenario: opts.scenario });
  if (opts.as) {
    const acc = MOCK_ACCOUNTS[opts.as];
    await client.login(acc.email, acc.password);
    if (opts.consented) await client.acceptConsent(CONSENT_VERSION);
  }
  return client;
}

/** Full app on the real route table (guards included). */
export async function renderApp(path: string, opts: RenderOpts = {}) {
  const client = await prepareClient(opts);
  const router = createTestRouter([path]);
  const user = userEvent.setup(opts.user);
  const utils = render(<App router={router} client={client} />);
  return { client, router, user, ...utils };
}

/** One page component without route guards (blocked-state cases). */
export async function renderPage(
  element: ReactElement,
  routePath: string,
  url: string,
  opts: RenderOpts = {},
) {
  const client = await prepareClient(opts);
  const user = userEvent.setup(opts.user);
  const qc = createQueryClient();
  const utils = render(
    <ApiProvider client={client}>
      <QueryClientProvider client={qc}>
        <CreatorProviders>
          <MemoryRouter initialEntries={[url]}>
            <Routes>
              <Route path={routePath} element={element} />
            </Routes>
          </MemoryRouter>
        </CreatorProviders>
      </QueryClientProvider>
    </ApiProvider>,
  );
  return { client, user, ...utils };
}

export function setupVideo() {
  installFakeVideo();
  fakeVideo.reset();
}

// ------------------------------------------------------------- scripting

export function patchSession(
  client: ApiClient,
  fn: (r: SessionDetailResponse) => SessionDetailResponse,
) {
  const getOrig = client.getSession.bind(client);
  const pollOrig = client.pollSession.bind(client);
  vi.spyOn(client, "getSession").mockImplementation((async (id: string, opts?: { include?: "facts" }) =>
    fn(structuredClone(await getOrig(id, opts)))) as typeof client.getSession);
  vi.spyOn(client, "pollSession").mockImplementation(async (...a) => {
    const r = await pollOrig(...a);
    if (r.notModified) return r;
    // The poll has no `facts`; give `fn` an empty list and drop it again.
    const patched: Partial<SessionDetailResponse> = fn({ ...structuredClone(r.data), facts: [] });
    delete patched.facts;
    return { ...r, data: patched as SessionSummaryResponse };
  });
}

export function patchDog(
  client: ApiClient,
  fn: (r: DogDetailResponse) => DogDetailResponse,
) {
  const orig = client.getDog.bind(client);
  vi.spyOn(client, "getDog").mockImplementation(async (...a) =>
    fn(structuredClone(await orig(...a))),
  );
}

export function patchMe(client: ApiClient, fn: (r: MeResponse) => MeResponse) {
  const orig = client.getMe.bind(client);
  vi.spyOn(client, "getMe").mockImplementation(async () => fn(structuredClone(await orig())));
}

export function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

export function makeFile(name: string, bytes = 1024, type = "video/quicktime"): File {
  const f = new File(["x"], name, { type });
  Object.defineProperty(f, "size", { value: bytes });
  return f;
}

export function isBlocked(el: HTMLElement): boolean {
  return (
    (el as HTMLButtonElement).disabled === true ||
    el.getAttribute("aria-disabled") === "true"
  );
}

/** The `<article>` whose heading matches. */
export function cardOf(container: HTMLElement | typeof document.body, name: RegExp | string) {
  return within(container as HTMLElement).getByRole("article", { name });
}
