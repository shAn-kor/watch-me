import { render, screen } from "@testing-library/react";
import { createMockClient } from "../api/mock";
import { App } from "./App";
import { createTestRouter } from "./router";

describe("app shell", () => {
  it("renders the dog list placeholder at /app", () => {
    render(<App router={createTestRouter(["/app"])} client={createMockClient()} />);
    expect(screen.getByText("Dog list (placeholder)")).toBeInTheDocument();
  });

  it("renders the public profile at /d/:slug", async () => {
    render(<App router={createTestRouter(["/d/k7m2q9x4tbwe"])} client={createMockClient()} />);
    expect(
      await screen.findByRole("heading", { level: 1, name: "Juniper" }),
    ).toBeInTheDocument();
  });

  it("shows the not-available page for unknown paths (no index page)", () => {
    render(<App router={createTestRouter(["/"])} client={createMockClient()} />);
    expect(screen.getByRole("heading", { name: "This profile is not available" })).toBeInTheDocument();
  });
});
