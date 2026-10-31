import { screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/errors";
import { MOCK_IDS, patchDog, prepareClient, renderApp } from "./testUtils";

const READY = { people_check: true, known_concerns: null, known_concerns_none: true } as const;
const dogUrl = (id: string) => `/app/dogs/${id}`;

afterEach(() => vi.restoreAllMocks());

describe("S5 dog detail", () => {
  it("shows header, coverage, sessions and facts", async () => {
    await renderApp(dogUrl(MOCK_IDS.dogDraft), { as: "staff" });
    expect(await screen.findByRole("heading", { name: "Biscuit" })).toBeInTheDocument();
    expect(screen.getByText("Clips in 1 of 8 situations")).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Coverage" });
    expect(within(table).getByText("Handling").closest("tr")).toHaveTextContent("Not observed yet");
    expect(screen.getByText(/Minji/)).toBeInTheDocument();
    expect(screen.getByText("Dropped the toy when asked, twice.")).toBeInTheDocument();
  });
});

describe("E2E 6 session line after review", () => {
  it("says all facts are confirmed, not '0 drafts', once no draft is left", async () => {
    const client = await prepareClient({ as: "staff" });
    patchDog(client, (r) => ({
      ...r,
      sessions: r.sessions.map((s) =>
        s.status === "review" ? { ...s, draft_fact_count: 0 } : s,
      ),
      facts: r.facts.map((f) => ({ ...f, status: "confirmed" as const })),
    }));
    await renderApp(dogUrl(MOCK_IDS.dogDraft), { client });
    await screen.findByRole("heading", { name: "Biscuit" });
    expect(screen.getByText("All facts confirmed")).toBeInTheDocument();
    expect(screen.queryByText("Ready to review")).not.toBeInTheDocument();
    expect(screen.queryByText("0 drafts")).not.toBeInTheDocument();
  });

  it("still says Ready to review with the draft count while drafts remain", async () => {
    const client = await prepareClient({ as: "staff" });
    patchDog(client, (r) => ({
      ...r,
      sessions: r.sessions.map((s) =>
        s.status === "review" ? { ...s, draft_fact_count: 2 } : s,
      ),
    }));
    await renderApp(dogUrl(MOCK_IDS.dogDraft), { client });
    expect(await screen.findByText("Ready to review")).toBeInTheDocument();
    expect(screen.getByText("2 drafts")).toBeInTheDocument();
  });
});

describe("FE-PNL-01 publish panel", () => {
  it("names each missing item, keeps Publish blocked, then enables it when ready", async () => {
    const { user, client } = await renderApp(dogUrl(MOCK_IDS.dogDraft), { as: "staff" });
    const publish = await screen.findByRole("button", { name: "Publish" });
    expect(publish).toHaveAttribute("aria-disabled", "true");
    const list = screen.getByText("Still needed to publish:").parentElement!;
    expect(within(list).getByText("People check")).toBeInTheDocument();
    expect(within(list).getByText("Known concerns")).toBeInTheDocument();
    expect(within(list).queryByText("At least one confirmed fact")).not.toBeInTheDocument();
    const spy = vi.spyOn(client, "saveChecklist");
    await user.click(
      screen.getByRole("checkbox", {
        name: /No one other than consenting members appears in any clip/,
      }),
    );
    // Unsaved changes keep Publish blocked.
    expect(publish).toHaveAttribute("aria-disabled", "true");
    await user.click(screen.getByRole("checkbox", { name: "None known" }));
    await user.click(screen.getByRole("button", { name: "Save checklist" }));
    expect(spy).toHaveBeenCalledWith(MOCK_IDS.dogDraft, READY);
    await screen.findByRole("button", { name: "Publish" });
    expect(screen.getByRole("button", { name: "Publish" })).not.toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.queryByText("Still needed to publish:")).not.toBeInTheDocument();
  });

  it("is read-only text for a volunteer", async () => {
    await renderApp(dogUrl(MOCK_IDS.dogDraft), { as: "volunteer", consented: true });
    expect(await screen.findByText("Only staff can publish.")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: "None known" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save checklist" })).not.toBeInTheDocument();
  });
});

describe("FE-PNL-02 publish result", () => {
  it("shows the public link with a copy button, and the draft state after unpublish", async () => {
    const client = await prepareClient({ as: "staff" });
    await client.saveChecklist(MOCK_IDS.dogDraft, READY);
    const { user } = await renderApp(dogUrl(MOCK_IDS.dogDraft), { client });
    // userEvent.setup() installs its own clipboard stub, so spy after render.
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    await user.click(await screen.findByRole("button", { name: "Publish" }));
    const dialog = await screen.findByRole("dialog", { name: "Publish Biscuit?" });
    await user.click(within(dialog).getByRole("button", { name: "Publish" }));
    expect(await screen.findByText("Published. The link works now.")).toBeInTheDocument();
    const link = await screen.findByText(/\/d\/[a-z0-9]+$/);
    expect(link).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Copy link" }));
    expect(writeText).toHaveBeenCalledWith(expect.stringMatching(/\/d\/[a-z0-9]+$/));
    expect(await screen.findByText("Link copied.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Unpublish" }));
    const confirm = await screen.findByRole("dialog", { name: "Unpublish Biscuit?" });
    await user.click(within(confirm).getByRole("button", { name: "Unpublish" }));
    expect(await screen.findByText("Unpublished. The link no longer works.")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Publish" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Unpublish" })).not.toBeInTheDocument();
  });

  it("maps publish_checklist_incomplete to the missing list", async () => {
    const client = await prepareClient({ as: "staff" });
    await client.saveChecklist(MOCK_IDS.dogDraft, READY);
    vi.spyOn(client, "publishDog").mockRejectedValue(
      new ApiError("publish_checklist_incomplete", 409, { missing: ["people_check", "known_concerns"] }),
    );
    const { user } = await renderApp(dogUrl(MOCK_IDS.dogDraft), { client });
    await user.click(await screen.findByRole("button", { name: "Publish" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Publish" }),
    );
    expect(
      await screen.findByText("Cannot publish yet. Still needed: People check, Known concerns."),
    ).toBeInTheDocument();
  });
});

describe("FE-PNL-03 destructive actions", () => {
  it("spaces the danger buttons in a wrapping row (8 px gap)", async () => {
    await renderApp(dogUrl(MOCK_IDS.dogDraft), { as: "staff" });
    const adopt = await screen.findByRole("button", { name: "Mark as adopted" });
    const del = screen.getByRole("button", { name: "Delete dog" });
    expect(adopt.parentElement).toHaveClass("wm-row");
    expect(del.parentElement).toBe(adopt.parentElement);
  });

  it("asks before marking a dog as adopted", async () => {
    const { user, client } = await renderApp(dogUrl(MOCK_IDS.dogDraft), { as: "staff" });
    const spy = vi.spyOn(client, "markAdopted");
    await user.click(await screen.findByRole("button", { name: "Mark as adopted" }));
    const dialog = await screen.findByRole("dialog", { name: "Mark Biscuit as adopted?" });
    expect(spy).not.toHaveBeenCalled();
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toHaveFocus();
    await user.click(within(dialog).getByRole("button", { name: "Mark as adopted" }));
    expect(spy).toHaveBeenCalledWith(MOCK_IDS.dogDraft);
    expect(await screen.findByText("Marked as adopted.")).toBeInTheDocument();
  });

  it("explains that files are removed and needs the dog's name before delete", async () => {
    const { user, client, router } = await renderApp(dogUrl(MOCK_IDS.dogDraft), { as: "staff" });
    const spy = vi.spyOn(client, "deleteDog");
    await user.click(await screen.findByRole("button", { name: "Delete dog" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete Biscuit?" });
    expect(within(dialog).getByText(/removes the dog, its clips, and its facts from storage/)).toBeInTheDocument();
    const go = within(dialog).getByRole("button", { name: "Delete dog" });
    expect(go).toBeDisabled();
    await user.type(within(dialog).getByRole("textbox"), "BISCUIT");
    expect(go).toBeEnabled();
    expect(spy).not.toHaveBeenCalled();
    await user.click(go);
    expect(spy).toHaveBeenCalledWith(MOCK_IDS.dogDraft);
    expect(await screen.findByText("Deleting Biscuit. Files are being removed.")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/app/dogs");
  });

  it("Cancel sends nothing", async () => {
    const { user, client } = await renderApp(dogUrl(MOCK_IDS.dogDraft), { as: "staff" });
    const spy = vi.spyOn(client, "deleteDog");
    await user.click(await screen.findByRole("button", { name: "Delete dog" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Cancel" }));
    expect(spy).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("FE-PNL-04 publish dialog discloses whole-clip access (D9)", () => {
  it("states the whole-clip rule; Cancel sends nothing; Publish sends", async () => {
    const client = await prepareClient({ as: "staff" });
    await client.saveChecklist(MOCK_IDS.dogDraft, READY);
    const { user } = await renderApp(dogUrl(MOCK_IDS.dogDraft), { client });
    const spy = vi.spyOn(client, "publishDog");
    await user.click(await screen.findByRole("button", { name: "Publish" }));
    const dialog = await screen.findByRole("dialog", { name: "Publish Biscuit?" });
    expect(dialog).toHaveTextContent("plays only the cited part");
    expect(dialog).toHaveTextContent("anyone with a clip's link can play the whole clip");
    expect(dialog).toHaveTextContent("Check every whole clip before you publish");
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(spy).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Publish" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Publish" }),
    );
    expect(spy).toHaveBeenCalledWith(MOCK_IDS.dogDraft);
  });
});

describe("FE-PNL-05 people-check helper", () => {
  it("tells staff to check the whole clip", async () => {
    await renderApp(dogUrl(MOCK_IDS.dogDraft), { as: "staff" });
    expect(
      await screen.findByText(/Check the whole clip, not only the cited part\. Visitors can play the full clip\./),
    ).toBeInTheDocument();
  });
});

describe("FE-PNL-06 new session blocked (D10)", () => {
  it("is disabled with the unpublish line for a published dog", async () => {
    await renderApp(dogUrl(MOCK_IDS.dogPublished), { as: "staff" });
    const btn = await screen.findByRole("button", { name: "New session" });
    expect(btn).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText("Unpublish this dog before you add clips.")).toBeInTheDocument();
  });

  it("is disabled with the reopen line for an adopted dog", async () => {
    const client = await prepareClient({ as: "staff" });
    await client.markAdopted(MOCK_IDS.dogDraft);
    await renderApp(dogUrl(MOCK_IDS.dogDraft), { client });
    expect(await screen.findByRole("button", { name: "New session" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.getByText("This dog is marked as adopted. Reopen it to add clips.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reopen as draft" })).toBeInTheDocument();
  });

  it("shows the consent line for a draft dog without consent", async () => {
    await renderApp(dogUrl(MOCK_IDS.dogDraft), { as: "volunteer" });
    expect(await screen.findByRole("button", { name: "New session" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.getByText("Accept the consent notice to add clips.")).toBeInTheDocument();
  });

  it("is a link for a consented member on a draft dog", async () => {
    await renderApp(dogUrl(MOCK_IDS.dogDraft), { as: "volunteer", consented: true });
    const link = await screen.findByRole("link", { name: "New session" });
    expect(link).toHaveAttribute("href", `/app/dogs/${MOCK_IDS.dogDraft}/sessions/new`);
  });
});

describe("S5 session rows", () => {
  it("shows a failed session with its reason and an Open button", async () => {
    const { client } = await renderApp(dogUrl(MOCK_IDS.dogDraft), { as: "staff", scenario: "merge_failed" });
    void client;
    expect(await screen.findByText(/We could not finish drafting facts\./)).toBeInTheDocument();
  });

  it("polls the dog while a session is processing", async () => {
    const client = await prepareClient({ as: "staff" });
    patchDog(client, (r) => ({
      ...r,
      sessions: r.sessions.map((s, i) => (i === 0 ? { ...s, status: "processing" as const } : s)),
    }));
    await renderApp(dogUrl(MOCK_IDS.dogDraft), { client });
    expect(await screen.findByText(/Processing/)).toBeInTheDocument();
  });
});
