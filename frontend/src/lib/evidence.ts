interface Ranged {
  clip_id: string;
  start_s: number;
}

/**
 * Evidence ranges in reading order: clip order first, then start time. The API
 * does not promise this order for creator facts, so the UI sorts. `clipRank`
 * maps a clip id to its position (the clip ordinal); clips without a rank keep
 * the order in which their clip first appears in the list.
 */
export function sortEvidence<T extends Ranged>(
  list: readonly T[],
  clipRank?: Readonly<Record<string, number>>,
): T[] {
  const firstSeen = new Map<string, number>();
  list.forEach((e, i) => {
    if (!firstSeen.has(e.clip_id)) firstSeen.set(e.clip_id, i);
  });
  const rank = (id: string) => clipRank?.[id] ?? firstSeen.get(id) ?? 0;
  return list
    .map((e, i) => ({ e, i }))
    .sort(
      (a, b) =>
        rank(a.e.clip_id) - rank(b.e.clip_id) ||
        a.e.start_s - b.e.start_s ||
        a.i - b.i,
    )
    .map((x) => x.e);
}
