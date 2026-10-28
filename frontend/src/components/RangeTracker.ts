/**
 * Framework-free watch logic for one evidence range (06 section 6.3, 05 P6-P7).
 * No React, no DOM: tests feed synthetic `timeupdate` sequences.
 *
 * Unique watched time is the union of the intervals between consecutive
 * samples inside [startS, endS]. A step of more than MAX_STEP_S (a scrub or a
 * stall) adds nothing, and replaying a covered part adds nothing.
 */

/** Largest sample-to-sample step that counts as playing (05 P6). */
export const MAX_STEP_S = 0.5;
/** The position must reach `end - END_TOLERANCE_S` (API 5.8). */
export const END_TOLERANCE_S = 0.5;
/** Share of the range that must be watched (API 5.8). */
export const MIN_WATCHED_SHARE = 0.8;

const EPS = 1e-6;

export interface RangeReport {
  positionS: number;
  watchedS: number;
}

/** The server rule of `POST /api/facts/{id}/playback-complete`. */
export function isRangeComplete(
  startS: number,
  endS: number,
  positionS: number,
  watchedS: number,
): boolean {
  return (
    positionS >= endS - END_TOLERANCE_S - EPS &&
    watchedS >= MIN_WATCHED_SHARE * (endS - startS) - EPS
  );
}

/** Round down to 0.1 s so a report never overstates what was watched. */
function floor01(x: number): number {
  return Math.floor(x * 10 + EPS * 10) / 10;
}

export class RangeTracker {
  readonly startS: number;
  readonly endS: number;
  /** Last sample inside the current continuous run; null after a seek or pause. */
  lastT: number | null = null;
  private position: number;
  private covered: [number, number][] = [];
  private reported = false;

  constructor(startS: number, endS: number) {
    this.startS = startS;
    this.endS = endS;
    this.position = startS;
  }

  /** Unique seconds watched, capped at the range length. */
  get watchedS(): number {
    let sum = 0;
    for (const [a, b] of this.covered) sum += b - a;
    return Math.min(sum, this.endS - this.startS);
  }

  onTimeUpdate(t: number): void {
    const prev = this.lastT;
    this.lastT = t;
    this.position = Math.min(Math.max(t, this.startS), this.endS);
    if (prev === null) return;
    const step = t - prev;
    if (step <= 0 || step > MAX_STEP_S + EPS) return;
    const a = Math.max(prev, this.startS);
    const b = Math.min(t, this.endS);
    if (b > a) this.addInterval(a, b);
  }

  /** A seek: the next sample only re-anchors, it adds nothing. */
  onSeek(t: number): void {
    this.lastT = null;
    this.position = Math.min(Math.max(t, this.startS), this.endS);
  }

  /** Pause, tab hidden, stall resume: wall time must not count. */
  onPause(): void {
    this.lastT = null;
  }

  isComplete(): boolean {
    return isRangeComplete(this.startS, this.endS, this.position, this.watchedS);
  }

  report(): RangeReport {
    return {
      positionS: floor01(this.position),
      watchedS: floor01(this.watchedS),
    };
  }

  /** The completion report once per play-through, then null until rearmed. */
  takeCompletion(): RangeReport | null {
    if (this.reported || !this.isComplete()) return null;
    this.reported = true;
    return this.report();
  }

  /** Allow another report but keep the coverage (05 P7: coverage accumulates). */
  rearm(): void {
    this.reported = false;
    this.lastT = null;
  }

  /** Forget everything (06 `reset()`). */
  reset(): void {
    this.covered = [];
    this.lastT = null;
    this.position = this.startS;
    this.reported = false;
  }

  private addInterval(a: number, b: number): void {
    const out: [number, number][] = [];
    let lo = a;
    let hi = b;
    for (const [x, y] of this.covered) {
      if (y < lo - EPS || x > hi + EPS) {
        out.push([x, y]);
      } else {
        lo = Math.min(lo, x);
        hi = Math.max(hi, y);
      }
    }
    out.push([lo, hi]);
    out.sort((p, q) => p[0] - q[0]);
    this.covered = out;
  }
}
