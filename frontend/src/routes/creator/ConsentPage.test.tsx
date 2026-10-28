import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MOCK_IDS, renderApp } from "./testUtils";

describe("FE-CON-01 consent screen", () => {
  it("keeps the button disabled until the box is ticked, then returns to the original route", async () => {
    const target = `/app/dogs/${MOCK_IDS.dogDraft}/sessions/new`;
    const { user, client, router } = await renderApp(target, { as: "volunteer" });
    const spy = vi.spyOn(client, "acceptConsent");
    const button = await screen.findByRole("button", { name: "Accept and continue" });
    expect(button).toBeDisabled();
    await user.click(
      screen.getByRole("checkbox", {
        name: "I agree that my face and voice may appear in clips I upload.",
      }),
    );
    expect(button).toBeEnabled();
    await user.click(button);
    expect(await screen.findByRole("heading", { name: "Capture rules" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe(target);
    expect(spy).toHaveBeenCalledWith("2026-10-28");
  });

  it("'Not now' leads to the dog list", async () => {
    const { user, router } = await renderApp("/app/consent", { as: "volunteer" });
    await user.click(await screen.findByRole("link", { name: "Not now" }));
    expect(await screen.findByRole("heading", { name: "Dogs" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/app/dogs");
  });

  it("shows the accepted state for a member who already accepted", async () => {
    await renderApp("/app/consent", { as: "staff" });
    expect(await screen.findByText(/You accepted this notice on/)).toBeInTheDocument();
    expect(screen.getByText("Back to dogs")).toBeInTheDocument();
  });
});
