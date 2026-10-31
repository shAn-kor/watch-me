import { describe, expect, it } from "vitest";
import { sortEvidence } from "./evidence";

const ev = (clip_id: string, start_s: number) => ({ clip_id, start_s });

describe("sortEvidence", () => {
  it("orders ranges of one clip by start time", () => {
    const out = sortEvidence([ev("a", 13), ev("a", 2)]);
    expect(out.map((e) => e.start_s)).toEqual([2, 13]);
  });

  it("orders by clip ordinal before start time", () => {
    const out = sortEvidence([ev("b", 1), ev("a", 30)], { a: 1, b: 2 });
    expect(out.map((e) => e.clip_id)).toEqual(["a", "b"]);
  });

  it("keeps API clip order when no ordinal is known", () => {
    const out = sortEvidence([ev("b", 20), ev("a", 5), ev("b", 3)]);
    expect(out).toEqual([ev("b", 3), ev("b", 20), ev("a", 5)]);
  });

  it("does not change the input", () => {
    const input = [ev("a", 13), ev("a", 2)];
    sortEvidence(input);
    expect(input[0]!.start_s).toBe(13);
  });
});
