/** Round to 0.1 s, the precision of clip ranges (01 section 1). */
export function roundTenth(s: number): number {
  return Math.round(s * 10) / 10;
}

/** Format seconds as `m:ss` (for example 75.4 gives `1:15`). */
export function formatClock(s: number): string {
  const total = Math.max(0, Math.floor(s));
  const m = Math.floor(total / 60);
  const sec = total % 60;
  return `${m}:${sec.toString().padStart(2, "0")}`;
}
