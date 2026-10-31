import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DogStatusChip, FactStatusChip } from "./Chips";

describe("E2E 6 status chips", () => {
  it.each([
    ["Confirmed", <FactStatusChip key="c" status="confirmed" />],
    ["Draft", <FactStatusChip key="d" status="draft" />],
    ["Published", <DogStatusChip key="p" status="published" />],
    ["Adopted", <DogStatusChip key="a" status="adopted" />],
  ])("%s shows the word and a drawn icon, no text glyph", (word, el) => {
    const { container } = render(el);
    const chip = container.firstElementChild!;
    expect(chip.textContent?.trim()).toBe(word);
    const icon = chip.querySelector("svg");
    expect(icon).not.toBeNull();
    expect(icon).toHaveAttribute("aria-hidden", "true");
  });
});
