import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/errors";
import { renderApp } from "./testUtils";

describe("S1 login", () => {
  it("shows the form when there is no session", async () => {
    await renderApp("/app/login");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveAttribute("autocomplete", "username");
    expect(screen.getByLabelText("Password")).toHaveAttribute("autocomplete", "current-password");
  });

  it("asks for both fields before sending", async () => {
    const { user, client } = await renderApp("/app/login");
    const spy = vi.spyOn(client, "login");
    await user.click(await screen.findByRole("button", { name: "Sign in" }));
    expect(screen.getByText("Enter your email.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });

  it("shows one message for wrong credentials", async () => {
    const { user } = await renderApp("/app/login");
    await user.type(await screen.findByLabelText("Email"), "staff@example.org");
    await user.type(screen.getByLabelText("Password"), "wrong");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Email or password is not correct.");
  });

  it("sends a consented member to the dog list", async () => {
    const { user, router } = await renderApp("/app/login");
    await user.type(await screen.findByLabelText("Email"), "staff@example.org");
    await user.type(screen.getByLabelText("Password"), "mock-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { name: "Dogs" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/app/dogs");
  });

  it("sends a member without consent to the consent notice once", async () => {
    const { user, router } = await renderApp("/app/login");
    await user.type(await screen.findByLabelText("Email"), "volunteer@example.org");
    await user.type(screen.getByLabelText("Password"), "mock-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(
      await screen.findByRole("heading", { name: "Faces and voices in clips" }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/app/consent");
  });

  it("goes to returnTo after login", async () => {
    const { user, router } = await renderApp("/app/login?returnTo=%2Fapp%2Fdogs%2Fnew");
    await user.type(await screen.findByLabelText("Email"), "staff@example.org");
    await user.type(screen.getByLabelText("Password"), "mock-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { name: "Add dog" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/app/dogs/new");
  });

  it("disables the button during a login rate limit", async () => {
    const { user, client } = await renderApp("/app/login");
    vi.spyOn(client, "login").mockRejectedValue(
      new ApiError("rate_limited", 429, { scope: "login" }, 300),
    );
    await user.type(await screen.findByLabelText("Email"), "a@example.org");
    await user.type(screen.getByLabelText("Password"), "x");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(
      await screen.findByText("Too many sign-in attempts. Try again in 5 minutes."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeDisabled();
  });

  it("shows the session-ended notice with returnTo", async () => {
    await renderApp("/app/login?returnTo=%2Fapp%2Fdogs&ended=1");
    expect(await screen.findByText(/Your session ended. Sign in again./)).toBeInTheDocument();
  });
});
