import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/errors";
import { MOCK_IDS, isBlocked, renderApp } from "./testUtils";

const url = (id: string) => `/app/dogs/${id}/sessions/new`;
const RULES_ACK = "I have read the capture rules.";

describe("FE-UPL-01 capture rules before filming", () => {
  it("blocks Start without the acknowledgement and sends capture_rules_ack:true after it", async () => {
    const { user, client, router } = await renderApp(url(MOCK_IDS.dogDraft), {
      as: "staff",
    });
    const spy = vi.spyOn(client, "createSession");
    expect(await screen.findByRole("heading", { name: "Capture rules" })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Capture rules" }).tagName).toBe("OL");
    const start = screen.getByRole("button", { name: "Start session" });
    await user.click(screen.getByRole("checkbox", { name: "Leash walk" }));
    expect(isBlocked(start)).toBe(true);
    await user.click(start);
    expect(spy).not.toHaveBeenCalled();
    await user.click(screen.getByRole("checkbox", { name: RULES_ACK }));
    expect(isBlocked(start)).toBe(false);
    await user.click(start);
    expect(spy).toHaveBeenCalledWith(
      MOCK_IDS.dogDraft,
      expect.objectContaining({ capture_rules_ack: true, situations: ["leash_walk"] }),
    );
    expect(await screen.findByRole("heading", { name: "Session" })).toBeInTheDocument();
    expect(router.state.location.pathname).toMatch(/^\/app\/sessions\/[0-9a-f]{32}$/);
  });

  it("needs at least one situation", async () => {
    const { user } = await renderApp(url(MOCK_IDS.dogDraft), { as: "staff" });
    await user.click(await screen.findByRole("checkbox", { name: RULES_ACK }));
    expect(isBlocked(screen.getByRole("button", { name: "Start session" }))).toBe(true);
  });

  it("shows the rules unticked on every new visit", async () => {
    const first = await renderApp(url(MOCK_IDS.dogDraft), { as: "staff" });
    await first.user.click(await screen.findByRole("checkbox", { name: RULES_ACK }));
    first.unmount();
    await renderApp(url(MOCK_IDS.dogDraft), { client: first.client });
    expect(await screen.findByRole("checkbox", { name: RULES_ACK })).not.toBeChecked();
  });

  it("shows coverage and a hint on each situation row", async () => {
    await renderApp(url(MOCK_IDS.dogDraft), { as: "staff" });
    const box = await screen.findByRole("checkbox", { name: "Handling" });
    expect(box).toHaveAccessibleDescription(
      expect.stringContaining("Touching paws, ears, or mouth; lifting; putting on a harness or collar."),
    );
    expect(box).toHaveAccessibleDescription(expect.stringContaining("Not observed yet"));
  });

  it("maps invalid_state to the dog-status line", async () => {
    const { user, client } = await renderApp(url(MOCK_IDS.dogDraft), { as: "staff" });
    vi.spyOn(client, "createSession").mockRejectedValue(new ApiError("invalid_state", 409));
    await user.click(await screen.findByRole("checkbox", { name: "Leash walk" }));
    await user.click(screen.getByRole("checkbox", { name: RULES_ACK }));
    await user.click(screen.getByRole("button", { name: "Start session" }));
    expect(
      await screen.findByText(
        "This dog cannot get new sessions right now. Open the dog page to see its status.",
      ),
    ).toBeInTheDocument();
  });

  it("is replaced by a message for a published dog (staff and volunteer)", async () => {
    const staff = await renderApp(url(MOCK_IDS.dogPublished), { as: "staff" });
    expect(
      await screen.findByText("This dog is published. Unpublish it before you add clips."),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to dog" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start session" })).not.toBeInTheDocument();
    staff.unmount();
    await renderApp(url(MOCK_IDS.dogPublished), { as: "volunteer", consented: true });
    expect(await screen.findByText("Ask staff to unpublish this dog.")).toBeInTheDocument();
  });
});
