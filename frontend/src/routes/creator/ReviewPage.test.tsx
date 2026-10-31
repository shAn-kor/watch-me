import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/errors";
import { hex } from "../../api/mock/fixtures";
import type { Fact, FactFlag } from "../../api/types";
import { playThrough } from "../../components/testing/fakeVideo";
import {
  MOCK_IDS,
  isBlocked,
  patchMe,
  patchSession,
  prepareClient,
  renderApp,
  setupVideo,
} from "./testUtils";

const sessionReview = (id: string = MOCK_IDS.sessionReview) => `/app/sessions/${id}/review`;
const F_LEASH = hex(0x60); // 1 range 12-21
const F_PERSON = hex(0x61); // 2 ranges 5-12, 30-37, warn flag
const EV_LEASH = hex(0x70);

beforeEach(() => setupVideo());
afterEach(() => vi.restoreAllMocks());

async function card(name: RegExp | string) {
  return screen.findByRole("article", { name });
}

/** Press Play on the card's current player and play the whole range. */
async function watch(user: UserEvent, c: HTMLElement, start: number, end: number) {
  const v = c.querySelector("video") as HTMLVideoElement;
  fireEvent.loadedMetadata(v);
  await user.click(within(c).getByRole("button", { name: "Play" }));
  playThrough(v, start, end);
}

function patchFact(client: Awaited<ReturnType<typeof prepareClient>>, id: string, over: Partial<Fact>) {
  patchSession(client, (r) => ({
    ...r,
    facts: r.facts.map((f) => (f.id === id ? { ...f, ...over } : f)),
  }));
}

describe("FE-CRD-01 confirm disabled until played", () => {
  it("stays blocked with the hint until every range is watched and saved", async () => {
    const { user, client } = await renderApp(sessionReview(), { as: "staff" });
    const report = vi.spyOn(client, "playbackComplete");
    const c = await card(/Meeting a new person/);
    const confirm = within(c).getByRole("button", { name: "Confirm" });
    expect(isBlocked(confirm)).toBe(true);
    expect(c).toHaveTextContent("Watch both ranges to confirm.");
    await user.click(within(c).getByRole("checkbox", { name: "I checked the wording." }));

    await watch(user, c, 5, 12);
    await waitFor(() => expect(report).toHaveBeenCalledTimes(1));
    expect(report.mock.calls[0]![0]).toBe(F_PERSON);
    expect(report.mock.calls[0]![1]).toMatchObject({ evidence_id: hex(0x71) });
    expect(report.mock.calls[0]![1].watched_s).toBeGreaterThanOrEqual(6.9);
    await within(c).findByText("Watched", { selector: "[data-range-state]" });
    expect(isBlocked(within(c).getByRole("button", { name: "Confirm" }))).toBe(true);
    expect(c).toHaveTextContent("Watch both ranges to confirm.");

    await user.click(within(c).getByRole("button", { name: /^Range 2 of 2/ }));
    await watch(user, c, 30, 37);
    await waitFor(() => expect(report).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(isBlocked(within(c).getByRole("button", { name: "Confirm" }))).toBe(false),
    );
  });

  it("confirms and says so", async () => {
    const { user, client } = await renderApp(sessionReview(), { as: "staff" });
    const confirmSpy = vi.spyOn(client, "confirmFact");
    const c = await card(/Leash walk/);
    await watch(user, c, 12, 21);
    await waitFor(() =>
      expect(isBlocked(within(c).getByRole("button", { name: "Confirm" }))).toBe(false),
    );
    await user.click(within(c).getByRole("button", { name: "Confirm" }));
    expect(confirmSpy).toHaveBeenCalledWith(F_LEASH, false);
    expect((await screen.findAllByText(/Fact confirmed\./)).length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "Confirmed" }));
    const lines = await screen.findAllByText(/Confirmed by Sam, staff/);
    expect(lines).toHaveLength(2);
  });
});

describe("FE-CRD-02 server says no", () => {
  it.each([
    ["staff_only_situation", "Only staff can confirm facts about children or cats."],
    ["not_own_session", "You can confirm only facts from your own sessions."],
    ["forbidden_role", "Only staff can confirm a staff note."],
  ] as const)("%s keeps Confirm blocked after local playback", async (code, hint) => {
    const client = await prepareClient({ as: "staff" });
    patchFact(client, F_LEASH, { can_confirm: false, blocked_reason: code });
    const { user } = await renderApp(sessionReview(), { client });
    const c = await card(/Leash walk/);
    expect(c).toHaveTextContent(hint);
    await watch(user, c, 12, 21);
    await within(c).findByText("Watched", { selector: "[data-range-state]" });
    expect(isBlocked(within(c).getByRole("button", { name: "Confirm" }))).toBe(true);
    expect(c).toHaveTextContent(hint);
  });
});

describe("FE-CRD-03 flags", () => {
  it("requires the wording box for a warn flag and sends acknowledge_flags:true", async () => {
    const { user, client } = await renderApp(sessionReview(), { as: "staff" });
    const spy = vi.spyOn(client, "confirmFact");
    const c = await card(/Meeting a new person/);
    expect(c).toHaveTextContent("Wording check");
    expect(c).toHaveTextContent('The word "friendly" states a trait.');
    await watch(user, c, 5, 12);
    await user.click(within(c).getByRole("button", { name: /^Range 2 of 2/ }));
    await watch(user, c, 30, 37);
    await within(c).findAllByText("Watched", { selector: "[data-range-state]" });
    const confirm = within(c).getByRole("button", { name: "Confirm" });
    await waitFor(() => expect(c).toHaveTextContent("Tick the wording box to confirm."));
    expect(isBlocked(confirm)).toBe(true);
    await user.click(confirm);
    expect(spy).not.toHaveBeenCalled();
    await user.click(within(c).getByRole("checkbox", { name: "I checked the wording." }));
    await user.click(within(c).getByRole("button", { name: "Confirm" }));
    expect(spy).toHaveBeenCalledWith(F_PERSON, true);
  });

  it("shows an info flag as a plain notice with no checkbox and no effect on Confirm", async () => {
    const client = await prepareClient({ as: "staff" });
    const flag: FactFlag = {
      code: "check_unavailable",
      severity: "info",
      source: "system",
      detail: "The wording check did not run.",
    };
    patchFact(client, F_LEASH, { flags: [flag] });
    const { user } = await renderApp(sessionReview(), { client });
    const spy = vi.spyOn(client, "confirmFact");
    const c = await card(/Leash walk/);
    expect(c).toHaveTextContent(
      "The wording check could not run for this fact. Read the text yourself.",
    );
    expect(within(c).queryByRole("checkbox", { name: "I checked the wording." })).not.toBeInTheDocument();
    await watch(user, c, 12, 21);
    await waitFor(() =>
      expect(isBlocked(within(c).getByRole("button", { name: "Confirm" }))).toBe(false),
    );
    await user.click(within(c).getByRole("button", { name: "Confirm" }));
    expect(spy).toHaveBeenCalledWith(F_LEASH, false);
  });

  it("treats an unknown severity as warn", async () => {
    const client = await prepareClient({ as: "staff" });
    const flag = { code: "banned_word", severity: "critical", source: "rules", detail: "x" } as unknown as FactFlag;
    patchFact(client, F_LEASH, { flags: [flag] });
    await renderApp(sessionReview(), { client });
    const c = await card(/Leash walk/);
    expect(within(c).getByRole("checkbox", { name: "I checked the wording." })).toBeInTheDocument();
  });
});

describe("FE-CRD-04 confirm error mapping", () => {
  it("shows the watch state for the listed ranges and refetches the list", async () => {
    const { user, client } = await renderApp(sessionReview(), {
      as: "staff",
      scenario: "playback_required",
    });
    vi.spyOn(client, "playbackComplete").mockResolvedValue({
      fact_id: F_LEASH,
      evidence_id: EV_LEASH,
      completed_at: "2026-10-28T00:00:00Z",
      all_ranges_played: true,
    });
    const reload = vi.spyOn(client, "getSession");
    const c = await card(/Leash walk/);
    await watch(user, c, 12, 21);
    await waitFor(() =>
      expect(isBlocked(within(c).getByRole("button", { name: "Confirm" }))).toBe(false),
    );
    const before = reload.mock.calls.length;
    await user.click(within(c).getByRole("button", { name: "Confirm" }));
    expect(await screen.findByText("Watch the whole range before you confirm.")).toBeInTheDocument();
    await waitFor(() => expect(reload.mock.calls.length).toBeGreaterThan(before));
    const again = await card(/Leash walk/);
    expect(within(again).getByText("Not watched", { selector: "[data-range-state]" })).toBeInTheDocument();
    expect(isBlocked(within(again).getByRole("button", { name: "Confirm" }))).toBe(true);
  });

  it("maps other confirm errors", async () => {
    const { user, client } = await renderApp(sessionReview(), { as: "staff", scenario: "playback_required" });
    vi.spyOn(client, "playbackComplete").mockResolvedValue({
      fact_id: F_LEASH, evidence_id: EV_LEASH, completed_at: "x", all_ranges_played: true,
    });
    vi.spyOn(client, "confirmFact").mockRejectedValue(new ApiError("invalid_state", 409));
    const c = await card(/Leash walk/);
    await watch(user, c, 12, 21);
    await waitFor(() => expect(isBlocked(within(c).getByRole("button", { name: "Confirm" }))).toBe(false));
    await user.click(within(c).getByRole("button", { name: "Confirm" }));
    expect(await screen.findByText("This fact changed since you opened it. The list will reload.")).toBeInTheDocument();
  });

  it("shows 'Watched, not saved' with Save when the report fails", async () => {
    const { user, client } = await renderApp(sessionReview(), { as: "staff" });
    vi.spyOn(client, "playbackComplete").mockRejectedValueOnce(new TypeError("Failed to fetch"));
    const c = await card(/Leash walk/);
    await watch(user, c, 12, 21);
    expect(await within(c).findByText("Watched, not saved", { selector: "[data-range-state]" })).toBeInTheDocument();
    expect(c).toHaveTextContent("Save your watch progress to confirm.");
    await user.click(within(c).getByRole("button", { name: "Save" }));
    await within(c).findByText("Watched", { selector: "[data-range-state]" });
  });
});

describe("FE-CRD-05 edit and delete", () => {
  it("PATCHes only the changed fields and updates the origin chip", async () => {
    const { user, client } = await renderApp(sessionReview(), { as: "staff" });
    const spy = vi.spyOn(client, "updateFact");
    const c = await card(/Leash walk/);
    expect(within(c).getByText("AI draft")).toBeInTheDocument();
    await user.click(within(c).getByRole("button", { name: "Edit" }));
    const sheet = await screen.findByRole("dialog", { name: "Edit fact" });
    const box = within(sheet).getByLabelText("What happens in the clip");
    await user.clear(box);
    await user.type(box, "Walked on a loose leash for the whole hallway.");
    await user.click(within(sheet).getByRole("button", { name: "Save changes" }));
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith(F_LEASH, { behavior: "Walked on a loose leash for the whole hallway." });
    const after = await card(/Leash walk/);
    expect(await within(after).findByText("Edited")).toBeInTheDocument();
    expect(await screen.findByText("Fact saved.")).toBeInTheDocument();
  });

  it("keeps Save changes blocked while nothing changed and checks the length client side", async () => {
    const { user, client } = await renderApp(sessionReview(), { as: "staff" });
    const spy = vi.spyOn(client, "updateFact");
    const c = await card(/Leash walk/);
    await user.click(within(c).getByRole("button", { name: "Edit" }));
    const sheet = await screen.findByRole("dialog", { name: "Edit fact" });
    const save = within(sheet).getByRole("button", { name: "Save changes" });
    await user.click(save);
    expect(spy).not.toHaveBeenCalled();
    const box = within(sheet).getByLabelText("What happens in the clip");
    await user.clear(box);
    await user.type(box, "Hi");
    await user.click(save);
    expect(within(sheet).getByText("Write between 3 and 280 characters.")).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });

  it("asks before deleting, then deletes", async () => {
    const { user, client } = await renderApp(sessionReview(), { as: "staff" });
    const spy = vi.spyOn(client, "deleteFact");
    const c = await card(/Leash walk/);
    await user.click(within(c).getByRole("button", { name: "Delete" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete this fact?" });
    expect(dialog).toHaveTextContent("It disappears from every page right away. This cannot be undone.");
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toHaveFocus();
    expect(spy).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: "Delete fact" }));
    expect(spy).toHaveBeenCalledWith(F_LEASH);
    await waitFor(() => expect(screen.queryByRole("article", { name: /Leash walk/ })).not.toBeInTheDocument());
    expect(await screen.findByText("Fact deleted.")).toBeInTheDocument();
  });

  it("warns that saving a confirmed fact sets it back to draft", async () => {
    const { user } = await renderApp(sessionReview(), { as: "staff" });
    await user.click(await screen.findByRole("button", { name: "All" }));
    const c = await card(/Food and toys/);
    await user.click(within(c).getByRole("button", { name: "Edit" }));
    const sheet = await screen.findByRole("dialog", { name: "Edit fact" });
    expect(sheet).toHaveTextContent(
      "Saving sets this fact back to draft. It leaves the public profile until you confirm it again.",
    );
  });
});

describe("FE-CRD-06 add fact", () => {
  const url = `/app/dogs/${MOCK_IDS.dogDraft}/review`;

  it("without a range saves a staff note", async () => {
    const { user, client } = await renderApp(url, { as: "staff" });
    const spy = vi.spyOn(client, "addFact");
    await user.click(await screen.findByRole("button", { name: "Add a fact by hand" }));
    const sheet = await screen.findByRole("dialog", { name: "Add a fact by hand" });
    await user.selectOptions(within(sheet).getByLabelText("Situation"), "handling");
    await user.type(within(sheet).getByLabelText("What happens in the clip"), "Accepted a brush on the back.");
    expect(sheet).toHaveTextContent(
      "This will be saved as: Shelter staff note. No clip. Only staff can confirm it.",
    );
    await user.click(within(sheet).getByRole("button", { name: "Add fact" }));
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy.mock.calls[0]![0]).toBe(MOCK_IDS.dogDraft);
    expect(spy.mock.calls[0]![1]).toMatchObject({ situation: "handling", behavior: "Accepted a brush on the back." });
    expect(spy.mock.calls[0]![1].evidence ?? []).toEqual([]);
    expect(await screen.findByText("Staff note added.")).toBeInTheDocument();
    const added = (await screen.findByText("Accepted a brush on the back.")).closest("article")!;
    expect(within(added).getByText("Shelter staff note")).toBeInTheDocument();
    expect(within(added).getByText("Added by hand")).toBeInTheDocument();
  });

  it("with a range saves a clip fact", async () => {
    const { user, client } = await renderApp(url, { as: "staff" });
    const spy = vi.spyOn(client, "addFact");
    await user.click(await screen.findByRole("button", { name: "Add a fact by hand" }));
    const sheet = await screen.findByRole("dialog", { name: "Add a fact by hand" });
    await user.selectOptions(within(sheet).getByLabelText("Situation"), "handling");
    await user.type(within(sheet).getByLabelText("What happens in the clip"), "Stood still for a brush.");
    await user.click(within(sheet).getByRole("checkbox", { name: "Attach a clip range" }));
    expect(sheet).toHaveTextContent(
      "This will be saved as: Seen in clip. You must watch the range and confirm it.",
    );
    const select = within(sheet).getByLabelText("Clip") as HTMLSelectElement;
    await user.selectOptions(select, select.options[1]!);
    await user.clear(within(sheet).getByLabelText("Start (s)"));
    await user.type(within(sheet).getByLabelText("Start (s)"), "2");
    await user.clear(within(sheet).getByLabelText("End (s)"));
    await user.type(within(sheet).getByLabelText("End (s)"), "8");
    await user.click(within(sheet).getByRole("button", { name: "Add fact" }));
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy.mock.calls[0]![1].evidence).toEqual([
      expect.objectContaining({ clip_id: select.options[1]!.value, start_s: 2, end_s: 8 }),
    ]);
    expect(await screen.findByText("Fact added. Watch the range, then confirm it.")).toBeInTheDocument();
    const added = (await screen.findByText("Stood still for a brush.")).closest("article")!;
    expect(within(added).getByText("Seen in clip", { exact: false })).toBeInTheDocument();
  });
});

describe("FE-CRD-07 flagged paraphrase text escaped", () => {
  it("renders markup as literal text", async () => {
    const client = await prepareClient({ as: "staff" });
    patchFact(client, F_LEASH, { behavior: "<b>x</b>" });
    await renderApp(sessionReview(), { client });
    const c = await card(/Leash walk/);
    expect(within(c).getByText("<b>x</b>")).toBeInTheDocument();
    expect(c.querySelector("b")).toBeNull();
  });
});

describe("FE-CRD-08 wording-check hint follows limits.wording_check", () => {
  it("rules_only: one line above the cards and no trait_claim chip", async () => {
    const client = await prepareClient({ as: "staff" });
    patchMe(client, (r) => ({ ...r, limits: { ...r.limits, wording_check: "rules_only" } }));
    patchFact(client, F_LEASH, {
      flags: [{ code: "trait_claim", severity: "warn", source: "model", detail: "States a trait." }],
    });
    await renderApp(sessionReview(), { client });
    await card(/Leash walk/);
    expect(screen.getAllByText("Wording check: banned-word list only.")).toHaveLength(1);
    expect(screen.queryByText(/may state a trait/)).not.toBeInTheDocument();
    expect(screen.queryByText("States a trait.")).not.toBeInTheDocument();
  });

  it("model: shows the heading about stated traits", async () => {
    await renderApp(sessionReview(), { as: "staff" });
    const c = await card(/Meeting a new person/);
    expect(c).toHaveTextContent(
      "Wording check: this text may state a trait, not something you can see in the clip.",
    );
    expect(screen.queryByText("Wording check: banned-word list only.")).not.toBeInTheDocument();
  });
});

describe("FE-CRD-09 clip with zero facts (D4)", () => {
  it("shows the note row and opens the add sheet with the clip preselected", async () => {
    const { user } = await renderApp(sessionReview(), { as: "staff", scenario: "zero_fact_clip" });
    const note = await screen.findByText(
      "Clip 3: No facts were drafted from this clip. Add one by hand if you saw something.",
    );
    const row = note.closest("li")!;
    expect(row).not.toHaveTextContent(/failed/i);
    await user.click(within(row).getByRole("button", { name: "Add a fact by hand" }));
    const sheet = await screen.findByRole("dialog", { name: "Add a fact by hand" });
    expect(within(sheet).getByRole("checkbox", { name: "Attach a clip range" })).toBeChecked();
    expect((within(sheet).getByLabelText("Clip") as HTMLSelectElement).value).toBe(hex(0x42));
  });

  it("shows no note when every ready clip is cited", async () => {
    await renderApp(sessionReview(), { as: "staff" });
    await card(/Leash walk/);
    expect(screen.queryByText(/No facts were drafted from this clip/)).not.toBeInTheDocument();
  });
});

describe("FE-CRD-10 session with no facts at all", () => {
  it("shows the empty text and the add-by-hand hint", async () => {
    const client = await prepareClient({ as: "staff" });
    patchSession(client, (r) => ({ ...r, facts: [] }));
    await renderApp(sessionReview(), { client });
    expect(await screen.findByText("No facts were drafted for this session.")).toBeInTheDocument();
    expect(
      screen.getByText("Add a fact by hand, or check that your clips have narration."),
    ).toBeInTheDocument();
  });
});

describe("S8 list, filters and redirects", () => {
  it("counts drafts and confirmed and filters", async () => {
    const { user } = await renderApp(sessionReview(), { as: "staff" });
    expect(await screen.findByText("2 to review - 1 confirmed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /To review/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("article", { name: /Food and toys/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Confirmed" }));
    const c = await card(/Food and toys/);
    expect(c).toHaveTextContent("Confirmed by Sam, staff, Oct 20, 2026");
    expect(screen.queryByRole("article", { name: /Leash walk/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "All" }));
    expect(await card(/Leash walk/)).toBeInTheDocument();
  });

  it("sends a session that is not in review to the session page", async () => {
    const { router } = await renderApp(sessionReview(MOCK_IDS.sessionMergeFailed), {
      as: "staff",
      scenario: "merge_failed",
    });
    await waitFor(() =>
      expect(router.state.location.pathname).toBe(`/app/sessions/${MOCK_IDS.sessionMergeFailed}`),
    );
  });

  it("shows the not-found text", async () => {
    await renderApp(sessionReview("0".repeat(32)), { as: "staff" });
    expect(await screen.findByText("This session was not found. It may have been deleted.")).toBeInTheDocument();
  });

  it("dog scope lists all facts of the dog", async () => {
    await renderApp(`/app/dogs/${MOCK_IDS.dogDraft}/review`, { as: "staff" });
    expect(await card(/Leash walk/)).toBeInTheDocument();
    expect(await card(/Meeting a new person/)).toBeInTheDocument();
  });

  it("a staff note shows no player", async () => {
    const client = await prepareClient({ as: "staff" });
    await client.addFact(MOCK_IDS.dogDraft, { situation: "handling", behavior: "Calm on the table." });
    await renderApp(`/app/dogs/${MOCK_IDS.dogDraft}/review`, { client });
    const c = (await screen.findByText("Calm on the table.")).closest("article")!;
    expect(c.querySelector("video")).toBeNull();
    expect(c).toHaveTextContent("No clip. This is a staff note.");
  });
});

describe("E2E 4 evidence ranges in time order", () => {
  it("lists ranges by clip order then start time, whatever order the API sent", async () => {
    const client = await prepareClient({ as: "staff" });
    patchSession(client, (r) => ({
      ...r,
      facts: r.facts.map((f) =>
        f.id === F_PERSON ? { ...f, evidence: [...f.evidence].reverse() } : f,
      ),
    }));
    await renderApp(sessionReview(), { client });
    const c = await card(/Meeting a new person/);
    const buttons = within(c).getAllByRole("button", { name: /^Range \d of 2/ });
    expect(buttons[0]).toHaveTextContent(/^Range 1 of 2 0:05-0:12/);
    expect(buttons[1]).toHaveTextContent(/^Range 2 of 2 0:30-0:37/);
  });
});
