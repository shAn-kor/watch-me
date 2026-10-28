import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderApp } from "./creator/testUtils";

describe("FE-STA-01 static pages", () => {
  it("/terms renders the terms text in the S11 order", async () => {
    await renderApp("/terms");
    expect(await screen.findByRole("heading", { level: 1, name: "Terms" })).toBeInTheDocument();
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings).toEqual([
      "What Watch Me! shows",
      "How facts are made",
      "Questions",
      "Adoption",
      "Your data",
      "Clips",
      "Whole clips",
      "Status of this page",
    ]);
    expect(
      screen.getByText(
        "Watch Me! does not take adoption applications or payments. Contact the shelter.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("This is a draft for the first release. It has not had a legal review."),
    ).toBeInTheDocument();
  });

  it.todo("terms is linked from the public profile footer (lane FE-P owns the profile footer)");
});
