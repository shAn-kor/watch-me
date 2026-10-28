import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MOCK_IDS, renderApp } from "../routes/creator/testUtils";

describe("FE-GRD-01 route guards", () => {
  it("sends a signed-out visitor to login and keeps the route", async () => {
    const { router } = await renderApp(`/app/dogs/${MOCK_IDS.dogDraft}`);
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/app/login");
    expect(new URLSearchParams(router.state.location.search).get("returnTo")).toBe(
      `/app/dogs/${MOCK_IDS.dogDraft}`,
    );
  });

  it("shows the consent page before the upload and confirm routes", async () => {
    for (const path of [
      `/app/dogs/${MOCK_IDS.dogDraft}/sessions/new`,
      `/app/sessions/${MOCK_IDS.sessionReview}`,
      `/app/sessions/${MOCK_IDS.sessionReview}/review`,
    ]) {
      const { router, unmount } = await renderApp(path, { as: "volunteer" });
      expect(
        await screen.findByRole("heading", { name: "Faces and voices in clips" }),
      ).toBeInTheDocument();
      expect(router.state.location.pathname).toBe("/app/consent");
      expect(new URLSearchParams(router.state.location.search).get("returnTo")).toBe(path);
      unmount();
    }
  });

  it("lets a member without consent open the dog list and a dog (Not now)", async () => {
    await renderApp(`/app/dogs`, { as: "volunteer" });
    expect(await screen.findByRole("heading", { name: "Dogs" })).toBeInTheDocument();
  });

  it("hides staff controls from a volunteer and shows them to staff", async () => {
    const vol = await renderApp(`/app/dogs/${MOCK_IDS.dogDraft}`, {
      as: "volunteer",
      consented: true,
    });
    expect(await screen.findByRole("heading", { name: "Biscuit" })).toBeInTheDocument();
    expect(screen.getByText("Only staff can publish.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Publish" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete dog" })).not.toBeInTheDocument();
    vol.unmount();

    await renderApp(`/app/dogs/${MOCK_IDS.dogDraft}`, { as: "staff" });
    expect(await screen.findByRole("button", { name: "Publish" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete dog" })).toBeInTheDocument();
  });

  it("redirects a signed-in member away from login", async () => {
    const { router } = await renderApp("/app/login", { as: "staff" });
    expect(await screen.findByRole("heading", { name: "Dogs" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/app/dogs");
  });

  it("redirects /app to the dog list", async () => {
    const { router } = await renderApp("/app", { as: "staff" });
    await waitFor(() => expect(router.state.location.pathname).toBe("/app/dogs"));
  });

  it("shows the app not-found page for other /app paths", async () => {
    await renderApp("/app/nothing-here", { as: "staff" });
    expect(await screen.findByText("This page does not exist.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to dogs" })).toBeInTheDocument();
  });
});
