/** Named mock scenarios (06 section 6.1): each makes one UI state reachable. */
export const SCENARIO_NAMES = [
  "happy",
  "failed_clip",
  "merge_failed",
  "zero_fact_clip",
  "rate_limited",
  "cost_cap",
  "hidden_profile",
  "playback_required",
] as const;

export type ScenarioName = (typeof SCENARIO_NAMES)[number];

export function isScenarioName(v: unknown): v is ScenarioName {
  return typeof v === "string" && (SCENARIO_NAMES as readonly string[]).includes(v);
}
