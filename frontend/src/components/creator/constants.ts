import type { Situation } from "../../api/types";

/** Version of the consent notice text on S2 (05 S2). */
export const CONSENT_VERSION = "2026-10-28";

/** One-line hints under each situation row (05 S6, from SERVICE section 10). */
export const SITUATION_HINTS: Readonly<Record<Situation, string>> = {
  new_person: "Approach, sniffing, jumping up, backing away.",
  handling: "Touching paws, ears, or mouth; lifting; putting on a harness or collar.",
  leash_walk: "Pulling, reaction to traffic, noise, or other dogs.",
  other_dog: "Through a fence or on leash.",
  food_toys: "Eating near a person, giving up a toy.",
  alone_time: "A short separation: barking, pacing, settling.",
  indoors_rest: "Settling on a bed, house-training notes.",
  children_cats: "Only film this when it actually happens. Staff confirm these facts.",
};

/** The five capture rules shown before every session (05 S6). */
export const CAPTURE_RULES: readonly string[] = [
  "Only the dog and you may be in the frame. You must have accepted the consent notice.",
  "Do not film other people, children included. Stop and start again if someone walks into the frame.",
  "Each clip is up to 2 minutes. A session takes up to 3 clips.",
  "Talk while you film. Say what the dog does and where you are. Korean or English both work.",
  "Film what happens, including moments that are hard to watch.",
];

export const PUBLISH_MISSING_LABEL = {
  people_check: "People check",
  known_concerns: "Known concerns",
  confirmed_fact: "At least one confirmed fact",
} as const;

export const MAX_PHOTO_BYTES = 8 * 1024 * 1024;
