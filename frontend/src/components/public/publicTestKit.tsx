import { render } from "@testing-library/react";
import { RouterProvider } from "react-router-dom";
import { vi } from "vitest";
import { createTestRouter } from "../../app/router";
import { ApiProvider } from "../../api/provider";
import type { ApiClient } from "../../api/client";
import { ApiError } from "../../api/errors";
import { createMockClient } from "../../api/mock";
import type {
  AnswerLine,
  ErrorCode,
  PublicEvidence,
  PublicFact,
  PublicProfile,
  QaAnswer,
  Situation,
} from "../../api/types";
import { SITUATIONS } from "../../lib/constants";

export const SLUG = "k7m2q9x4tbwe";

export function evidence(clip: string, a: number, b: number, captions = true): PublicEvidence {
  return {
    clip_id: clip,
    start_s: a,
    end_s: b,
    media_url: `/media/${clip}.mp4`,
    captions_url: captions ? `/media/${clip}.vtt` : null,
  };
}

export function fact(id: string, behavior: string, over: Partial<PublicFact> = {}): PublicFact {
  const ev = over.evidence ?? [evidence(`clip-${id}`, 12, 21)];
  return {
    id,
    behavior,
    source: ev.length ? "clip" : "staff_note",
    source_label: ev.length ? "Seen in clip" : "Staff note",
    observed_on: "2026-10-28",
    confirmed_by_label: "Confirmed by volunteer",
    clip_length: { clip_count: ev.length, seconds: 9, label: ev.length ? "1 clip, 9 s" : "No clip" },
    notice: null,
    evidence: ev,
    ...over,
  };
}

export function profile(over: Partial<PublicProfile> = {}): PublicProfile {
  return {
    banner_id: "pub0_v1",
    dog: {
      slug: SLUG,
      name: "Biscuit",
      sex: "male",
      age_estimate: "about 3 years",
      size: "medium",
      location: "Portland, OR",
      photo_url: "/media/dogs/d1/photo.jpg",
      published_at: "2026-10-28T10:00:00Z",
    },
    org: { name: "Maple Street Rescue", country: "US" },
    coverage: {
      situations_total: 8,
      situations_covered: 2,
      summary: "ignored",
      by_situation: SITUATIONS.map(({ code, label }) => ({
        situation: code,
        label,
        covered: code === "leash_walk" || code === "food_toys",
        clip_count: code === "leash_walk" ? 2 : code === "food_toys" ? 1 : 0,
        filmed_s: code === "leash_walk" ? 74 : code === "food_toys" ? 31 : 0,
        confirmed_s: code === "leash_walk" ? 16 : code === "food_toys" ? 7 : 0,
      })),
    },
    known_concerns: { none_known: false, text: "Pulls hard toward other dogs on leash." },
    facts_by_situation: [
      {
        situation: "leash_walk",
        label: "Leash walk",
        facts: [fact("f1", "Walked beside the handler on a loose leash.")],
      },
      {
        situation: "children_cats",
        label: "Children or cats",
        facts: [
          fact("f2", "Looked at the shelter cat for 4 seconds.", {
            notice: {
              code: "ask_shelter_in_person_meeting",
              text: "Ask the shelter about an in-person meeting.",
            },
          }),
        ],
      },
    ],
    not_observed: SITUATIONS.filter(
      (s) => s.code !== "leash_walk" && s.code !== "food_toys",
    ).map(({ code, label }) => ({ situation: code as Situation, label })),
    contact: { url: "https://shelter.example.org", email: "adopt@example.org", phone: null },
    ask: { enabled: true, max_question_chars: 300, limit_per_hour: 10 },
    ...over,
  };
}

export function line(id: string, text: string, over: Partial<AnswerLine> = {}): AnswerLine {
  const f = fact(id, text);
  return {
    fact_id: id,
    text,
    situation: "leash_walk",
    situation_label: "Leash walk",
    source_label: f.source_label,
    observed_on: f.observed_on,
    confirmed_by_label: f.confirmed_by_label,
    clip_length: f.clip_length,
    notice: null,
    evidence: f.evidence,
    ...over,
  };
}

export function answer(over: Partial<QaAnswer> = {}): QaAnswer {
  return {
    outcome: "answered",
    heading: "Here is what has been filmed:",
    lines: [line("f1", "Walked beside the handler on a loose leash.")],
    cited_fact_ids: ["f1"],
    limits: { remaining_this_hour: 8 },
    ...over,
  };
}

export function apiError(
  code: ErrorCode,
  status: number,
  details: Record<string, unknown> = {},
  retryAfter: number | null = null,
): ApiError {
  return new ApiError(code, status, details as never, retryAfter);
}

/** Mock client whose public calls are replaced by the given results. */
export function clientWith(opts: {
  profile?: PublicProfile | Error;
  ask?: QaAnswer | Error;
}): ApiClient {
  const client = createMockClient();
  const p = opts.profile ?? profile();
  vi.spyOn(client, "getPublicProfile").mockImplementation(() =>
    p instanceof Error ? Promise.reject(p) : Promise.resolve(p),
  );
  if (opts.ask) {
    const a = opts.ask;
    vi.spyOn(client, "ask").mockImplementation(() =>
      a instanceof Error ? Promise.reject(a) : Promise.resolve(a),
    );
  }
  return client;
}

export function renderAt(client: ApiClient, path: string) {
  return render(
    <ApiProvider client={client}>
      <RouterProvider router={createTestRouter([path])} />
    </ApiProvider>,
  );
}
