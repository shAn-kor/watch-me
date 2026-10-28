import { act, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiClient } from "../../api/client";
import { ApiError } from "../../api/errors";
import type { Clip } from "../../api/types";
import SessionPage from "./SessionPage";
import {
  MOCK_IDS,
  deferred,
  makeFile,
  patchDog,
  patchSession,
  prepareClient,
  renderApp,
  renderPage,
} from "./testUtils";

const sessionUrl = (id: string) => `/app/sessions/${id}`;

async function newSession(client: ApiClient, dogId = MOCK_IDS.dogDraft) {
  const { session } = await client.createSession(dogId, {
    situations: ["leash_walk"],
    capture_rules_ack: true,
  });
  return session.id;
}

function fakeTimers() {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  return { advanceTimers: (ms: number) => vi.advanceTimersByTime(ms) };
}
async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

beforeEach(() => {
  vi.useRealTimers();
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("FE-UPL-02 upload states", () => {
  it("shows uploading percent, then uploaded, the processing step, then ready", async () => {
    const client = await prepareClient({ as: "staff" });
    const id = await newSession(client);
    const real = client.uploadClip.bind(client);
    const gate = deferred<void>();
    vi.spyOn(client, "uploadClip").mockImplementation(async (sid, file, opts) => {
      opts?.onProgress?.(42, 100);
      const res = await real(sid, file, { clientRequestId: opts?.clientRequestId });
      await gate.promise;
      return res;
    });
    const { user } = await renderApp(sessionUrl(id), { client, user: fakeTimers() });
    await user.upload(
      await screen.findByLabelText("Choose from library"),
      makeFile("IMG_0412.mov"),
    );
    const bar = await screen.findByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "42");
    expect(screen.getByText("Uploading 42%")).toBeInTheDocument();
    expect(screen.getByText(/IMG_0412\.mov/)).toBeInTheDocument();
    gate.resolve();
    expect(await screen.findByText("Uploaded. Waiting to start.")).toBeInTheDocument();
    await advance(3000);
    expect(await screen.findByText("Step 2 of 4: Listening to narration")).toBeInTheDocument();
    await advance(3000);
    expect(await screen.findByText("Ready")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Watch clip" })).toBeInTheDocument();
  });
});

describe("FE-UPL-03 error causes", () => {
  const rows: [string, ApiError | Error, string, boolean][] = [
    ["unsupported_file_type", new ApiError("unsupported_file_type", 415, { allowed: [".mp4"] }), "This file type is not supported. Use an MP4 or MOV video.", false],
    ["probe_timeout", new ApiError("unsupported_file_type", 415, { reason: "probe_timeout" }), "We could not read this video in time. Try again, or choose a different file.", true],
    ["file_too_large", new ApiError("file_too_large", 413, { max_bytes: 209715200 }), "This file is larger than 200 MB. Choose a smaller file or film a shorter clip.", false],
    ["clip_too_long", new ApiError("clip_too_long", 422, { max_s: 120, duration_s: 150 }), "This clip is 150 s long. The limit is 2 minutes (120 s). Trim it or film a shorter clip.", false],
    ["upload_incomplete", new ApiError("upload_incomplete", 400), "The upload stopped before it finished. Check your connection and try again.", true],
    ["network", new TypeError("Failed to fetch"), "The upload stopped before it finished. Check your connection and try again.", true],
    ["clip_limit_reached", new ApiError("clip_limit_reached", 409), "This session already has 3 clips. Delete one to add another.", false],
    ["storage_unavailable", new ApiError("storage_unavailable", 503), "The server cannot store files right now. Try again in a few minutes.", true],
    ["rate_limited", new ApiError("rate_limited", 429, { scope: "member" }, 120), "You have reached the limit of 20 uploads per hour. Try again in 2 minutes.", true],
    ["not_own_session", new ApiError("not_own_session", 403), "Only the member who started this session, or staff, can add clips.", false],
  ];
  it.each(rows)("%s shows its own cause", async (_name, err, text, retry) => {
    const client = await prepareClient({ as: "staff" });
    const id = await newSession(client);
    vi.spyOn(client, "uploadClip").mockRejectedValue(err);
    const { user } = await renderApp(sessionUrl(id), { client });
    await user.upload(await screen.findByLabelText("Choose from library"), makeFile("a.mov"));
    expect(await screen.findByText(text)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" }) !== null).toBe(retry);
    expect(screen.getByRole("button", { name: "Remove" })).toBeInTheDocument();
  });

  it("retry reuses the same client_request_id", async () => {
    const client = await prepareClient({ as: "staff" });
    const id = await newSession(client);
    const real = client.uploadClip.bind(client);
    const spy = vi
      .spyOn(client, "uploadClip")
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockImplementation(real);
    const { user } = await renderApp(sessionUrl(id), { client });
    await user.upload(await screen.findByLabelText("Choose from library"), makeFile("a.mov"));
    await user.click(await screen.findByRole("button", { name: "Try again" }));
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(2));
    const ids = spy.mock.calls.map((c) => c[2]?.clientRequestId);
    expect(ids[0]).toBeTruthy();
    expect(ids[1]).toBe(ids[0]);
  });
});

describe("FE-UPL-04 client prechecks", () => {
  it("rejects a 201 MiB file and an .avi without sending", async () => {
    const client = await prepareClient({ as: "staff" });
    const id = await newSession(client);
    const spy = vi.spyOn(client, "uploadClip");
    const { user } = await renderApp(sessionUrl(id), { client, user: { applyAccept: false } });
    const input = await screen.findByLabelText("Choose from library");
    await user.upload(input, makeFile("big.mov", 201 * 1024 * 1024));
    expect(
      await screen.findByText(
        "This file is larger than 200 MB. Choose a smaller file or film a shorter clip.",
      ),
    ).toBeInTheDocument();
    await user.upload(input, makeFile("old.avi", 1000, "video/x-msvideo"));
    expect(
      await screen.findByText("This file type is not supported. Use an MP4 or MOV video."),
    ).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });

  it("offers a camera input and a library input with the spec attributes", async () => {
    const client = await prepareClient({ as: "staff" });
    const id = await newSession(client);
    await renderApp(sessionUrl(id), { client });
    const cam = await screen.findByLabelText("Record with camera");
    expect(cam).toHaveAttribute("accept", "video/*");
    expect(cam).toHaveAttribute("capture", "environment");
    expect(screen.getByLabelText("Choose from library")).toHaveAttribute(
      "accept",
      ".mp4,.mov,video/mp4,video/quicktime",
    );
  });
});

describe("FE-UPL-05 failed clip actions", () => {
  it("shows the cause, Try again and Delete clip for a retryable failure", async () => {
    const { user, client } = await renderApp(sessionUrl(MOCK_IDS.sessionReview), {
      as: "staff",
      scenario: "failed_clip",
    });
    const retry = vi.spyOn(client, "retryClip");
    expect(await screen.findByText("Transcription failed. Try again.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Delete clip" })).toBeInTheDocument();
  });

  it("offers only delete for a clip that cannot be retried", async () => {
    const client = await prepareClient({ as: "staff", scenario: "failed_clip" });
    patchSession(client, (r) => ({
      ...r,
      clips: r.clips.map((c) =>
        c.status === "failed"
          ? { ...c, fail_code: "too_long" as const, error: { cause: "The clip is longer than 2 minutes.", retryable: false } }
          : c,
      ),
    }));
    await renderApp(sessionUrl(MOCK_IDS.sessionReview), { client });
    expect(await screen.findByText("The clip is longer than 2 minutes.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
    expect(screen.getByText("Delete this clip and upload a different file.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete clip" })).toBeInTheDocument();
  });

  it("confirms before deleting a clip and reports what was removed", async () => {
    const { user, client } = await renderApp(sessionUrl(MOCK_IDS.sessionReview), {
      as: "staff",
      scenario: "failed_clip",
    });
    const del = vi.spyOn(client, "deleteClip");
    await user.click(await screen.findByRole("button", { name: "Delete clip" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete this clip?" });
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toHaveFocus();
    expect(del).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: "Delete clip" }));
    expect(del).toHaveBeenCalledTimes(1);
    expect(await screen.findByText(/Clip deleted\./)).toBeInTheDocument();
  });
});

describe("FE-UPL-06 polling", () => {
  it("polls every 3 s with If-None-Match and stops at review", async () => {
    const client = await prepareClient({ as: "staff" });
    const id = await newSession(client);
    await client.uploadClip(id, makeFile("a.mov"));
    await client.submitSession(id);
    const spy = vi.spyOn(client, "pollSession");
    await renderApp(sessionUrl(id), { client, user: fakeTimers() });
    expect(await screen.findByRole("heading", { name: "Drafting facts" })).toBeInTheDocument();
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy.mock.calls[0]![1] ?? null).toBeNull();
    await advance(3000);
    await waitFor(() => expect(spy.mock.calls.length).toBeGreaterThanOrEqual(2));
    expect(spy.mock.calls[1]![1]).toEqual(expect.any(String));
    await advance(3000);
    expect(await screen.findByText("Facts are ready to review.")).toBeInTheDocument();
    const n = spy.mock.calls.length;
    await advance(12000);
    expect(spy.mock.calls.length).toBe(n);
  });

  it("does not poll an open session with no active clip", async () => {
    const client = await prepareClient({ as: "staff" });
    const id = await newSession(client);
    const spy = vi.spyOn(client, "pollSession");
    await renderApp(sessionUrl(id), { client, user: fakeTimers() });
    await screen.findByText("Add your first clip.");
    await advance(12000);
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("shows a quiet connection line after 3 failed polls and keeps trying", async () => {
    const client = await prepareClient({ as: "staff" });
    const id = await newSession(client);
    await client.uploadClip(id, makeFile("a.mov"));
    await client.submitSession(id);
    const real = client.pollSession.bind(client);
    let fail = false;
    vi.spyOn(client, "pollSession").mockImplementation(async (...a) => {
      if (fail) throw new TypeError("Failed to fetch");
      return real(...a);
    });
    await renderApp(sessionUrl(id), { client, user: fakeTimers() });
    await screen.findByRole("heading", { name: "Drafting facts" });
    fail = true;
    for (let i = 0; i < 4; i++) await advance(3000);
    expect(await screen.findByText("Connection problem. Trying again.")).toBeInTheDocument();
  });
});

describe("FE-UPL-07 no_audio_track warning", () => {
  it("shows a non-blocking notice", async () => {
    const client = await prepareClient({ as: "staff" });
    const id = await newSession(client);
    const real = client.uploadClip.bind(client);
    vi.spyOn(client, "uploadClip").mockImplementation(async (...a) => ({
      ...(await real(...a)),
      warnings: ["no_audio_track"],
    }));
    const { user } = await renderApp(sessionUrl(id), { client });
    await user.upload(await screen.findByLabelText("Choose from library"), makeFile("a.mov"));
    expect(
      await screen.findByText("This clip has no sound. It will have no narration and no captions."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Draft facts" })).toBeInTheDocument();
  });
});

describe("FE-UPL-08 retry merge button (D6)", () => {
  const MERGE_TEXT = "We could not finish drafting facts.";

  it("shows Retry merge to the owner, sends the call and switches to Processing", async () => {
    const { user, client } = await renderApp(sessionUrl(MOCK_IDS.sessionMergeFailed), {
      as: "volunteer",
      consented: true,
      scenario: "merge_failed",
    });
    const spy = vi.spyOn(client, "retryMerge");
    expect(await screen.findByText(MERGE_TEXT)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry merge" }));
    expect(spy).toHaveBeenCalledWith(MOCK_IDS.sessionMergeFailed);
    expect(await screen.findByRole("heading", { name: "Drafting facts" })).toBeInTheDocument();
    expect(screen.queryByText(MERGE_TEXT)).not.toBeInTheDocument();
  });

  it("shows it to staff", async () => {
    await renderApp(sessionUrl(MOCK_IDS.sessionMergeFailed), { as: "staff", scenario: "merge_failed" });
    expect(await screen.findByRole("button", { name: "Retry merge" })).toBeInTheDocument();
  });

  it("hides it from another volunteer", async () => {
    const client = await prepareClient({ as: "volunteer", consented: true, scenario: "merge_failed" });
    patchSession(client, (r) => ({ ...r, session: { ...r.session, member_id: "f".repeat(32), owner_name: "Other" } }));
    await renderApp(sessionUrl(MOCK_IDS.sessionMergeFailed), { client });
    expect(await screen.findByText("This session belongs to another member.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry merge" })).not.toBeInTheDocument();
  });

  it("hides it without consent", async () => {
    await renderPage(<SessionPage />, "/app/sessions/:sessionId", sessionUrl(MOCK_IDS.sessionMergeFailed), {
      as: "volunteer",
      scenario: "merge_failed",
    });
    expect(await screen.findByText("Accept the consent notice before you upload.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry merge" })).not.toBeInTheDocument();
  });

  it("shows the try-again text and no button for no_usable_clip", async () => {
    const client = await prepareClient({ as: "staff", scenario: "merge_failed" });
    patchSession(client, (r) => ({ ...r, session: { ...r.session, fail_code: "no_usable_clip" } }));
    await renderApp(sessionUrl(MOCK_IDS.sessionMergeFailed), { client });
    expect(
      await screen.findByText(
        "No clip could be processed. Try a failed clip again, or start a new session and upload new clips.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry merge" })).not.toBeInTheDocument();
  });

  it.each([
    ["not_own_session", "Only the member who started this session, or staff, can retry it."],
    ["invalid_state", "This session is not waiting for a retry. Reload the page."],
    ["consent_required", "Accept the consent notice before you upload."],
  ] as const)("maps %s", async (code, text) => {
    const { user, client } = await renderApp(sessionUrl(MOCK_IDS.sessionMergeFailed), {
      as: "staff",
      scenario: "merge_failed",
    });
    vi.spyOn(client, "retryMerge").mockRejectedValue(new ApiError(code, 403));
    await user.click(await screen.findByRole("button", { name: "Retry merge" }));
    expect(await screen.findByText(text)).toBeInTheDocument();
  });
});

describe("FE-UPL-09 add buttons blocked for non-draft dog (D10)", () => {
  const asOpen = (r: Parameters<Parameters<typeof patchSession>[1]>[0]) => ({
    ...r,
    session: { ...r.session, status: "open" as const },
    clips: [] as Clip[],
    facts: [],
  });

  it.each([
    ["published", "published"],
    ["adopted", "adopted"],
  ] as const)("disables adding clips for a %s dog", async (_n, status) => {
    const client = await prepareClient({ as: "staff" });
    patchSession(client, asOpen);
    patchDog(client, (r) => ({ ...r, dog: { ...r.dog, status } }));
    await renderApp(sessionUrl(MOCK_IDS.sessionPublished), { client });
    expect(
      await screen.findByText(
        `This dog is ${status}. Staff must unpublish or reopen it before you add clips.`,
      ),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Choose from library")).toBeDisabled();
    expect(screen.getByLabelText("Record with camera")).toBeDisabled();
  });

  it("shows its own line without consent", async () => {
    const client = await prepareClient({ as: "volunteer" });
    patchSession(client, asOpen);
    await renderPage(<SessionPage />, "/app/sessions/:sessionId", sessionUrl(MOCK_IDS.sessionReview), { client });
    expect(await screen.findByText("Accept the consent notice before you upload.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open consent notice" })).toBeInTheDocument();
    expect(screen.getByLabelText("Choose from library")).toBeDisabled();
  });
});

describe("FE-UPL-10 review-ready box", () => {
  it("shows the box with Review facts only when the session is in review", async () => {
    await renderApp(sessionUrl(MOCK_IDS.sessionReview), { as: "staff" });
    expect(await screen.findByText("Facts are ready to review.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review facts" })).toHaveAttribute(
      "href",
      `/app/sessions/${MOCK_IDS.sessionReview}/review`,
    );
  });

  it("does not show the box while drafting, and a retried session goes back to Drafting facts", async () => {
    const client = await prepareClient({ as: "staff", scenario: "failed_clip" });
    let retried = false;
    const realRetry = client.retryClip.bind(client);
    vi.spyOn(client, "retryClip").mockImplementation(async (id) => {
      retried = true;
      return realRetry(id);
    });
    patchSession(client, (r) =>
      retried ? { ...r, session: { ...r.session, status: "processing" as const, review_ready_at: null } } : r,
    );
    const { user } = await renderApp(sessionUrl(MOCK_IDS.sessionReview), { client });
    expect(await screen.findByText("Facts are ready to review.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "Drafting facts" })).toBeInTheDocument();
    expect(screen.queryByText("Facts are ready to review.")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Review facts" })).not.toBeInTheDocument();
  });
});

describe("S7 session actions", () => {
  it("submits with Draft facts and then shows Drafting facts", async () => {
    const client = await prepareClient({ as: "staff" });
    const id = await newSession(client);
    await client.uploadClip(id, makeFile("a.mov"));
    const submit = vi.spyOn(client, "submitSession");
    const { user } = await renderApp(sessionUrl(id), { client });
    await user.click(await screen.findByRole("button", { name: "Draft facts" }));
    expect(submit).toHaveBeenCalledWith(id);
    expect(await screen.findByRole("heading", { name: "Drafting facts" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Draft facts" })).not.toBeInTheDocument();
  });

  it("opens Watch clip in a sheet with the preview player", async () => {
    const { user } = await renderApp(sessionUrl(MOCK_IDS.sessionReview), { as: "staff" });
    const watch = await screen.findAllByRole("button", { name: "Watch clip" });
    await user.click(watch[0]!);
    const dialog = await screen.findByRole("dialog");
    expect(dialog.querySelector("video")).not.toBeNull();
  });

  it("shows read-only text to a member who is not the owner", async () => {
    await renderApp(sessionUrl(MOCK_IDS.sessionPublished), { as: "volunteer", consented: true });
    expect(await screen.findByText("This session belongs to another member.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Choose from library")).not.toBeInTheDocument();
  });

  it("shows not-found text with a link back to dogs", async () => {
    await renderApp(sessionUrl("0".repeat(32)), { as: "staff" });
    expect(
      await screen.findByText("This session was not found. It may have been deleted."),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to dogs" })).toBeInTheDocument();
  });
});
