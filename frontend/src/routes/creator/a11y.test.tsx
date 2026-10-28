import { screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { beforeEach, describe, expect, it } from "vitest";
import { MOCK_IDS, renderApp, setupVideo, type RenderOpts } from "./testUtils";

beforeEach(() => setupVideo());

async function critical(container: HTMLElement) {
  const results = await axe(container, {
    rules: { "color-contrast": { enabled: false }, region: { enabled: false } },
  });
  return results.violations.filter((v) => v.impact === "critical").map((v) => v.id);
}

const screens: [string, string, RenderOpts, string | RegExp][] = [
  ["login", "/app/login", {}, "Sign in"],
  ["consent", "/app/consent", { as: "volunteer" }, "Faces and voices in clips"],
  ["dog list", "/app/dogs", { as: "staff" }, "Dogs"],
  ["dog new", "/app/dogs/new", { as: "staff" }, "Add dog"],
  ["dog detail", `/app/dogs/${MOCK_IDS.dogDraft}`, { as: "staff" }, "Biscuit"],
  ["session new", `/app/dogs/${MOCK_IDS.dogDraft}/sessions/new`, { as: "staff" }, "New session"],
  ["session", `/app/sessions/${MOCK_IDS.sessionReview}`, { as: "staff", scenario: "failed_clip" }, "Session"],
  ["review", `/app/sessions/${MOCK_IDS.sessionReview}/review`, { as: "staff" }, "Review"],
  ["terms", "/terms", {}, "Terms"],
];

describe("FE-A11-01 accessibility smoke", () => {
  it.each(screens)("%s has no critical violations", async (_n, path, opts, heading) => {
    const { container } = await renderApp(path, opts);
    await screen.findByRole("heading", { level: 1, name: heading });
    if (path.endsWith("/review")) await screen.findByRole("article", { name: /Leash walk/ });
    expect(await critical(container)).toEqual([]);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("every button has an accessible name", async () => {
    await renderApp(`/app/sessions/${MOCK_IDS.sessionReview}/review`, { as: "staff" });
    await screen.findByRole("article", { name: /Leash walk/ });
    for (const b of screen.getAllByRole("button")) {
      expect(b).toHaveAccessibleName();
    }
  });

  it("a review video has a captions track when the URL exists and none otherwise", async () => {
    await renderApp(`/app/sessions/${MOCK_IDS.sessionReview}/review`, { as: "staff" });
    const withCaps = (await screen.findByRole("article", { name: /Leash walk/ })).querySelector("video")!;
    expect(withCaps.querySelector('track[kind="captions"]')).not.toBeNull();
    const noCaps = screen.getByRole("article", { name: /Meeting a new person/ }).querySelector("video")!;
    expect(noCaps.querySelector("track")).toBeNull();
  });
});
