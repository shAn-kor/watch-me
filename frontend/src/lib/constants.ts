import type { Situation } from "../api/types";

/** Situation codes and labels in PRD order (01 section 2). */
export const SITUATIONS: readonly { code: Situation; label: string }[] = [
  { code: "new_person", label: "Meeting a new person" },
  { code: "handling", label: "Handling" },
  { code: "leash_walk", label: "Leash walk" },
  { code: "other_dog", label: "Meeting another dog" },
  { code: "food_toys", label: "Food and toys" },
  { code: "alone_time", label: "Alone time" },
  { code: "indoors_rest", label: "Indoors and rest" },
  { code: "children_cats", label: "Children or cats" },
] as const;

export const SITUATION_LABELS: Readonly<Record<Situation, string>> =
  Object.fromEntries(SITUATIONS.map((s) => [s.code, s.label])) as Record<
    Situation,
    string
  >;

/** Fallback used before `GET /api/me` answers; the server's `limits` win. */
export const LIMITS_FALLBACK = {
  max_clip_bytes: 209_715_200,
  max_clip_s: 120,
  max_clips_per_session: 3,
  allowed_extensions: [".mp4", ".mov"],
  wording_check: "model",
} as const;

/** Safety banner version the frontend renders (PUB-0). Compared with the API `banner_id`. */
export const BANNER_ID = "pub0_v1";

/** Session polling interval while clips are active (06 section 6.4). */
export const POLL_INTERVAL_MS = 3000;
