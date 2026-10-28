import { describe, expect, it } from "vitest";
import { RangeTracker, isRangeComplete } from "./RangeTracker";

/** Feed `timeupdate` samples from a to b in `step` second increments. */
function play(tr: RangeTracker, a: number, b: number, step = 0.25) {
  const n = Math.round((b - a) / step);
  for (let i = 0; i <= n; i++) tr.onTimeUpdate(a + i * step);
}

describe("FE-RNG RangeTracker", () => {
  it("FE-RNG-01 normal play", () => {
    const tr = new RangeTracker(12, 21);
    for (let t = 12; t <= 19.5; t += 0.25) {
      tr.onTimeUpdate(t);
      // Never complete before the position reaches end - 0.5.
      expect(tr.isComplete()).toBe(false);
    }
    // watched >= 7.2 already here, but the position is below 20.5.
    expect(tr.report().watchedS).toBeGreaterThanOrEqual(7.2);
    for (let t = 19.75; t <= 20.25; t += 0.25) tr.onTimeUpdate(t);
    expect(tr.isComplete()).toBe(false);
    tr.onTimeUpdate(20.5);
    expect(tr.isComplete()).toBe(true);
    for (let t = 20.75; t <= 21; t += 0.25) tr.onTimeUpdate(t);
    expect(tr.report().watchedS).toBeCloseTo(9.0, 1);
    expect(tr.report().positionS).toBeCloseTo(21.0, 1);
    expect(tr.isComplete()).toBe(true);
  });

  it("FE-RNG-02 scrub to the end", () => {
    const tr = new RangeTracker(12, 21);
    tr.onTimeUpdate(12);
    tr.onSeek(20.9);
    tr.onTimeUpdate(21.0);
    expect(tr.report().watchedS).toBeCloseTo(0, 0);
    expect(tr.isComplete()).toBe(false);
  });

  it("FE-RNG-03 skipping part", () => {
    const tr = new RangeTracker(12, 21);
    play(tr, 12, 14);
    tr.onTimeUpdate(19); // jump of 5 s adds nothing
    play(tr, 19, 21);
    expect(tr.report().watchedS).toBeCloseTo(4, 1);
    expect(tr.isComplete()).toBe(false); // needs 7.2 s
  });

  it("FE-RNG-04 pause and resume: wall time never counts", () => {
    const tr = new RangeTracker(12, 21);
    play(tr, 12, 15);
    tr.onPause();
    // 30 s of wall time pass with no events, then playback resumes.
    play(tr, 15, 16);
    expect(tr.report().watchedS).toBeCloseTo(4, 1);
  });

  it("FE-RNG-04 an explicit pause also ignores the gap to the resume position", () => {
    const tr = new RangeTracker(12, 21);
    play(tr, 12, 13);
    tr.onPause();
    tr.onTimeUpdate(13.4); // first sample after resume only re-anchors
    expect(tr.report().watchedS).toBeCloseTo(1, 1);
  });

  it("FE-RNG-05 replay reports a second completion, not a duplicate", () => {
    const tr = new RangeTracker(12, 21);
    play(tr, 12, 21);
    const first = tr.takeCompletion();
    expect(first).not.toBeNull();
    expect(first!.watchedS).toBeCloseTo(9, 1);
    // Same play-through: not reported twice.
    tr.onTimeUpdate(21);
    expect(tr.takeCompletion()).toBeNull();
    tr.reset();
    expect(tr.report().watchedS).toBe(0);
    expect(tr.isComplete()).toBe(false);
    play(tr, 12, 21);
    expect(tr.takeCompletion()).not.toBeNull();
    expect(tr.takeCompletion()).toBeNull();
  });

  it("FE-RNG-05 rearm keeps coverage but allows a new report", () => {
    const tr = new RangeTracker(12, 21);
    play(tr, 12, 21);
    expect(tr.takeCompletion()).not.toBeNull();
    tr.rearm();
    expect(tr.report().watchedS).toBeCloseTo(9, 1);
    expect(tr.takeCompletion()).not.toBeNull();
  });

  it("replaying a covered part adds no watched time (P6)", () => {
    const tr = new RangeTracker(0, 10);
    play(tr, 0, 4);
    tr.onSeek(0);
    play(tr, 0, 4);
    expect(tr.report().watchedS).toBeCloseTo(4, 1);
  });

  it("ignores samples outside the range and steps over 0.5 s", () => {
    const tr = new RangeTracker(10, 20);
    play(tr, 8, 10); // before the range
    tr.onTimeUpdate(10.4);
    tr.onTimeUpdate(11.0); // 0.6 s step: not counted
    expect(tr.report().watchedS).toBeLessThan(1);
    play(tr, 19, 22);
    expect(tr.report().watchedS).toBeLessThan(3);
    expect(tr.report().positionS).toBeLessThanOrEqual(20);
  });

  it("report rounds down to 0.1 s so it never overstates", () => {
    const tr = new RangeTracker(0, 100);
    tr.onTimeUpdate(0);
    tr.onTimeUpdate(0.29);
    expect(tr.report().watchedS).toBe(0.2);
  });
});

describe("FE-RNG-06 thresholds equal the server", () => {
  // From API-PBK-02: position end - 0.6 / end - 0.5; watched 0.79 / 0.8 of length.
  const start = 12;
  const end = 21;
  const len = end - start;
  const table: [number, number, boolean][] = [
    [end - 0.6, len, false],
    [end - 0.5, len, true],
    [end, 0.79 * len, false],
    [end, 0.8 * len, true],
    [end - 0.5, 0.8 * len, true],
    [end - 0.6, 0.8 * len, false],
    [end, len, true],
    [start, 0, false],
  ];
  it.each(table)("position %s watched %s -> %s", (p, w, expected) => {
    // Server rule: position >= end - 0.5 and watched >= 0.8 * length.
    const server = p >= end - 0.5 && w >= 0.8 * len;
    expect(server).toBe(expected);
    expect(isRangeComplete(start, end, p, w)).toBe(expected);
  });
});
