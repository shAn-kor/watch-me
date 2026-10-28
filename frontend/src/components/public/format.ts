const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

/** `2026-10-28` gives `Oct 28, 2026`. No Date object, so no time zone shift. */
export function formatDay(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  const month = MONTHS[Number(m[2]) - 1];
  if (!month) return iso;
  return `${month} ${Number(m[3])}, ${m[1]}`;
}

export function plural(n: number, one: string, many: string): string {
  return n === 1 ? one : many;
}

export const SEX_LABEL = {
  male: "Male",
  female: "Female",
  unknown: "Unknown",
} as const;
