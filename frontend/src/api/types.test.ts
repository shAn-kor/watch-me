import { BANNER_ID, SITUATIONS } from "../lib/constants";
import { ApiError } from "./errors";
import type {
  ErrorEnvelope,
  Fact,
  MeResponse,
  PublicProfile,
  QaAnswer,
  Situation,
} from "./types";

// Type-level checks: a drift makes `tsc` (pnpm build) fail.
type Equal<A, B> =
  (<T>() => T extends A ? 1 : 2) extends <T>() => T extends B ? 1 : 2
    ? true
    : false;
const situationsMatch: Equal<(typeof SITUATIONS)[number]["code"], Situation> =
  true;

const envelope: ErrorEnvelope = {
  error: {
    code: "playback_required",
    message: "Watch the whole clip range before you confirm this fact.",
    details: { missing_evidence_ids: ["a1b2c3d4e5f60718293a4b5c6d7e8f90"] },
  },
};

describe("api contract types", () => {
  it("compiles sample bodies from 01", () => {
    const me: MeResponse = {
      member: {
        id: "9f1c",
        email: "vol@example.org",
        display_name: "Minji",
        role: "volunteer",
        consented_at: null,
        consent_version: null,
      },
      org: {
        id: "3b7d",
        name: "Maple Street Rescue",
        country: "US",
        location: null,
        contact: { url: null, email: "adopt@example.org", phone: null },
      },
      csrf_token: "6f2a",
      limits: {
        max_clip_bytes: 209715200,
        max_clip_s: 120,
        max_clips_per_session: 3,
        allowed_extensions: [".mp4", ".mov"],
        wording_check: "model",
      },
    };
    const partialFact: Pick<Fact, "can_confirm" | "blocked_reason"> = {
      can_confirm: false,
      blocked_reason: "playback_required",
    };
    const answer: Pick<QaAnswer, "outcome"> = { outcome: "not_observed" };
    const banner: Pick<PublicProfile, "banner_id"> = { banner_id: BANNER_ID };
    expect(situationsMatch).toBe(true);
    expect(me.member.role).toBe("volunteer");
    expect(partialFact.blocked_reason).toBe("playback_required");
    expect(answer.outcome).toBe("not_observed");
    expect(banner.banner_id).toBe("pub0_v1");
  });

  it("ApiError carries code, status, details and retryAfter", () => {
    const e = new ApiError(
      envelope.error.code,
      409,
      envelope.error.details,
      null,
      envelope.error.message,
    );
    expect(e).toBeInstanceOf(Error);
    expect(e.code).toBe("playback_required");
    expect(e.status).toBe(409);
    expect(e.details.missing_evidence_ids).toHaveLength(1);
    expect(e.retryAfter).toBeNull();
  });

  it("lists the 8 situations in PRD order", () => {
    expect(SITUATIONS.map((s) => s.code)).toEqual([
      "new_person",
      "handling",
      "leash_walk",
      "other_dog",
      "food_toys",
      "alone_time",
      "indoors_rest",
      "children_cats",
    ]);
  });
});
