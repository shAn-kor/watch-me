import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/errors";
import { makeFile, renderApp } from "./testUtils";

describe("S4 dog create", () => {
  it("validates on submit with the spec texts", async () => {
    const { user, client } = await renderApp("/app/dogs/new", { as: "staff" });
    const spy = vi.spyOn(client, "createDog");
    await user.click(await screen.findByRole("button", { name: "Save dog" }));
    expect(screen.getByText("Enter a name of 1 to 60 characters.")).toBeInTheDocument();
    expect(screen.getByText("Enter an age estimate of 1 to 40 characters.")).toBeInTheDocument();
    expect(screen.getAllByText("Choose one option.")).toHaveLength(2);
    expect(spy).not.toHaveBeenCalled();
  });

  it("creates the dog and opens its page", async () => {
    const { user, client, router } = await renderApp("/app/dogs/new", { as: "staff" });
    const spy = vi.spyOn(client, "createDog");
    await user.type(await screen.findByLabelText("Name"), "Pepper");
    await user.click(screen.getByRole("radio", { name: "Female" }));
    await user.type(screen.getByLabelText("Age estimate"), "about 2 years");
    await user.click(screen.getByRole("radio", { name: "Small" }));
    await user.click(screen.getByRole("button", { name: "Save dog" }));
    expect(await screen.findByRole("heading", { name: "Pepper" })).toBeInTheDocument();
    expect(spy).toHaveBeenCalledWith(
      expect.objectContaining({ name: "Pepper", sex: "female", age_estimate: "about 2 years", size: "small" }),
    );
    expect(router.state.location.pathname).toMatch(/^\/app\/dogs\/[0-9a-f]{32}$/);
  });

  it("keeps the dog and shows the photo error when the photo fails", async () => {
    const { user, client, router } = await renderApp("/app/dogs/new", { as: "staff" });
    vi.spyOn(client, "uploadDogPhoto").mockRejectedValue(
      new ApiError("unsupported_file_type", 415),
    );
    await user.type(await screen.findByLabelText("Name"), "Pepper");
    await user.click(screen.getByRole("radio", { name: "Female" }));
    await user.type(screen.getByLabelText("Age estimate"), "about 2 years");
    await user.click(screen.getByRole("radio", { name: "Small" }));
    await user.upload(
      screen.getByLabelText("Choose photo"),
      makeFile("pic.heic", 100, "image/heic"),
    );
    await user.click(screen.getByRole("button", { name: "Save dog" }));
    expect(
      await screen.findByText("This photo type is not supported. Use JPEG, PNG, or HEIC."),
    ).toBeInTheDocument();
    expect(await screen.findByText("Dog saved. The photo was not uploaded.")).toBeInTheDocument();
    expect(router.state.location.pathname).toMatch(/\/edit$/);
  });
});
