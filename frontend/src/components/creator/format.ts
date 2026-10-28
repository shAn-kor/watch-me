const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** `2026-10-28` as a calendar date, never shifted by a time zone (05 section 0). */
export function formatDay(day: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(day);
  if (!m) return day;
  return `${MONTHS[Number(m[2]) - 1] ?? m[2]} ${Number(m[3])}, ${m[1]}`;
}

/** An RFC 3339 instant shown as a local calendar date: `Oct 28, 2026`. */
export function formatInstant(ts: string): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return `${MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
}

/** Today as `YYYY-MM-DD` in the local time zone. */
export function todayLocal(): string {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mm}-${dd}`;
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return n === 1 ? one : many;
}

/** `Try again in {n} seconds` / minutes for 60 s and more (05 section 2.3). */
export function waitText(seconds: number | null): string {
  if (seconds === null) return "Try again in a moment.";
  if (seconds >= 60) {
    const m = Math.ceil(seconds / 60);
    return `Try again in ${m} ${plural(m, "minute")}.`;
  }
  const s = Math.max(1, Math.ceil(seconds));
  return `Try again in ${s} ${plural(s, "second")}.`;
}

export function round01(x: number): number {
  return Math.round(x * 10) / 10;
}

/** Same-origin absolute URL for a public path. */
export function absoluteUrl(path: string): string {
  return `${window.location.origin}${path}`;
}

/** Accept only in-app return paths (no open redirect). */
export function safeReturnTo(v: string | null): string | null {
  if (!v) return null;
  if (!v.startsWith("/app") || v.startsWith("//")) return null;
  return v;
}

export const SEX_LABEL = { male: "Male", female: "Female", unknown: "Unknown" } as const;
export const SIZE_LABEL = { small: "Small", medium: "Medium", large: "Large" } as const;
