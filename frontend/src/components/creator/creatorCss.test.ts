import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(join(__dirname, "creator.css"), "utf8");

function rule(selector: string): string {
  const i = css.indexOf(`${selector} {`);
  expect(i, selector).toBeGreaterThanOrEqual(0);
  return css.slice(i, css.indexOf("}", i));
}

describe("E2E 5 tap targets", () => {
  it("checkbox rows are at least 44 px tall and the label stretches over the row", () => {
    expect(rule(".wm-check")).toContain("min-height: 44px");
    expect(rule(".wm-check label")).toContain("min-height: 44px");
    expect(rule(".wm-check label")).toContain("flex: 1");
    expect(rule(".wm-check label::before")).toContain("inset: 0");
  });

  it("toasts do not take pointer events, except the dismissable error toast", () => {
    expect(rule(".wm-toasts")).toContain("pointer-events: none");
    expect(rule(".wm-toast--error")).toContain("pointer-events: auto");
  });
});
