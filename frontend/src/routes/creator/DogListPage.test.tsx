import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { prepareClient, renderApp } from "./testUtils";

describe("FE-LST-01 dog list coverage", () => {
  it("shows 'n of 8' and the counts for each of 3 dogs", async () => {
    const client = await prepareClient({ as: "staff" });
    await client.createDog({ name: "Moss", sex: "male", age_estimate: "about 5 years", size: "large" });
    await renderApp("/app/dogs", { client });
    const list = await screen.findByRole("list", { name: "Dogs" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    const { dogs } = await client.listDogs();
    for (const d of dogs) {
      const row = rows.find((r) => within(r).queryByText(d.dog.name))!;
      expect(row).toBeTruthy();
      expect(
        within(row).getByText(`Clips in ${d.coverage.situations_covered} of 8 situations`),
      ).toBeInTheDocument();
      const { draft_facts, confirmed_facts, clips } = d.counts;
      if (draft_facts + confirmed_facts > 0 || clips > 0) {
        expect(
          within(row).getByText(`${draft_facts} drafts to review - ${confirmed_facts} confirmed`),
        ).toBeInTheDocument();
      }
    }
  });

  it("links each row to the dog with a full accessible name", async () => {
    await renderApp("/app/dogs", { as: "staff" });
    const link = await screen.findByRole("link", { name: /^Biscuit, draft, clips in 1 of 8 situations/ });
    expect(link).toHaveAttribute("href", expect.stringMatching(/^\/app\/dogs\/[0-9a-f]{32}$/));
  });

  it("shows the empty state", async () => {
    const client = await prepareClient({ as: "staff" });
    vi.spyOn(client, "listDogs").mockResolvedValue({ dogs: [] });
    await renderApp("/app/dogs", { client });
    expect(await screen.findByText("No dogs yet.")).toBeInTheDocument();
    expect(screen.getByText("Add the first dog to start a profile.")).toBeInTheDocument();
  });

  it("shows the consent line only while consent is missing", async () => {
    const vol = await renderApp("/app/dogs", { as: "volunteer" });
    expect(
      await screen.findByText("Accept the consent notice before you add clips."),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open consent notice" })).toBeInTheDocument();
    vol.unmount();
    await renderApp("/app/dogs", { as: "staff" });
    await screen.findByRole("heading", { name: "Dogs" });
    expect(screen.queryByText("Accept the consent notice before you add clips.")).not.toBeInTheDocument();
  });

  it("menu lists Dogs, Consent notice, Terms and Sign out, and signing out goes to login", async () => {
    const { user, router } = await renderApp("/app/dogs", { as: "staff" });
    await user.click(await screen.findByRole("button", { name: "Menu" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("link", { name: "Dogs" })).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: "Consent notice" })).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: "Terms" })).toHaveAttribute("href", "/terms");
    expect(within(dialog).getByText(/Sam/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/app/login");
  });
});
