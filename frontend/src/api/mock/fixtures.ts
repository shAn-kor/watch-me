import type {
  Clip,
  Dog,
  DogSize,
  Evidence,
  Fact,
  FactFlag,
  Id,
  Limits,
  Member,
  Org,
  Session,
  Situation,
} from "../types";
import type { ScenarioName } from "./scenarios";

export const MOCK_ACCOUNTS = {
  staff: { email: "staff@example.org", password: "mock-password" },
  volunteer: { email: "volunteer@example.org", password: "mock-password" },
} as const;

/** Slug of the published sample dog; its profile is served by the mock. */
export const MOCK_PUBLIC_SLUG = "k7m2q9x4tbwe";

/** Static sample media (served from `public/mock/`, 06 section 6.2). */
export const MOCK_MEDIA_URL = "/mock/sample.mp4";
export const MOCK_CAPTIONS_URL = "/mock/sample.vtt";
export const MOCK_PHOTO_URL = "/mock/dog.jpg";

export const MOCK_LIMITS: Limits = {
  max_clip_bytes: 209_715_200,
  max_clip_s: 120,
  max_clips_per_session: 3,
  allowed_extensions: [".mp4", ".mov"],
  wording_check: "model",
};

export const MOCK_ORG: Org = {
  id: hex(1),
  name: "Maple Street Rescue",
  country: "US",
  location: "Portland, OR",
  contact: { url: null, email: "adopt@example.org", phone: null },
};

export function hex(n: number): Id {
  return n.toString(16).padStart(32, "0");
}

export const IDS = {
  staff: hex(0x10),
  volunteer: hex(0x11),
  dogDraft: hex(0x20),
  dogPublished: hex(0x21),
  sessionReview: hex(0x30),
  sessionMergeFailed: hex(0x31),
  sessionPublished: hex(0x32),
} as const;

const T0 = "2026-10-20T09:00:00Z";
const DAY = "2026-10-20";

export interface MockState {
  members: (Member & { password: string })[];
  org: Org;
  dogs: Dog[];
  checklists: Record<Id, {
    people_check: boolean;
    people_check_at: string | null;
    known_concerns: string | null;
    known_concerns_none: boolean;
  }>;
  sessions: Session[];
  clips: Clip[];
  deletedClips: Set<Id>;
  facts: Fact[];
  deletedFacts: Set<Id>;
  /** Evidence ids whose range this mock member has played. */
  played: Set<Id>;
  nextId: number;
}

function member(
  id: Id,
  email: string,
  name: string,
  role: Member["role"],
  consented: boolean,
  password: string,
): Member & { password: string } {
  return {
    id,
    email,
    display_name: name,
    role,
    consented_at: consented ? T0 : null,
    consent_version: consented ? "2026-10-28" : null,
    password,
  };
}

function dog(id: Id, name: string, size: DogSize, status: Dog["status"], slug: string | null): Dog {
  return {
    id,
    name,
    sex: "male",
    age_estimate: "about 3 years",
    size,
    location: "Portland, OR",
    photo_url: MOCK_PHOTO_URL,
    status,
    public_slug: slug,
    public_path: slug ? `/d/${slug}` : null,
    created_by: IDS.staff,
    created_at: T0,
    published_at: status === "published" ? T0 : null,
    adopted_at: null,
  };
}

function clip(
  n: number,
  sessionId: Id,
  ordinal: number,
  over: Partial<Clip> = {},
): Clip {
  const id = hex(n);
  return {
    id,
    session_id: sessionId,
    ordinal,
    original_filename: `IMG_${1000 + n}.mov`,
    original_size_bytes: 48_000_000,
    duration_s: 60,
    has_audio: true,
    status: "ready",
    step: null,
    fail_code: null,
    error: null,
    media_url: MOCK_MEDIA_URL,
    captions_url: MOCK_CAPTIONS_URL,
    created_at: T0,
    ready_at: T0,
    ...over,
  };
}

export function evidence(
  n: number,
  clipId: Id,
  startS: number,
  endS: number,
  captions = true,
): Evidence {
  return {
    id: hex(n),
    clip_id: clipId,
    start_s: startS,
    end_s: endS,
    played_by_me: false,
    media_url: MOCK_MEDIA_URL,
    captions_url: captions ? MOCK_CAPTIONS_URL : null,
  };
}

export function clipLength(ev: Evidence[]): Fact["clip_length"] {
  const seconds = Math.round(ev.reduce((s, e) => s + (e.end_s - e.start_s), 0) * 10) / 10;
  return {
    clip_count: new Set(ev.map((e) => e.clip_id)).size,
    seconds,
    label: ev.length === 0 ? "No video" : `${seconds} s of video`,
  };
}

function fact(
  n: number,
  dogId: Id,
  sessionId: Id | null,
  situation: Situation,
  behavior: string,
  ev: Evidence[],
  over: Partial<Fact> = {},
  flags: FactFlag[] = [],
): Fact {
  return {
    id: hex(n),
    dog_id: dogId,
    session_id: sessionId,
    situation,
    behavior,
    source: ev.length ? "clip" : "staff_note",
    origin: "ai_unchanged",
    status: "draft",
    flags,
    observed_on: DAY,
    evidence: ev,
    clip_length: clipLength(ev),
    confirmed: null,
    created_by: null,
    can_confirm: false,
    blocked_reason: ev.length ? "playback_required" : null,
    ...over,
  };
}

const CONFIRMED_BY = {
  by_member_id: IDS.staff,
  by_name: "Sam",
  role: "staff" as const,
  at: T0,
};

/** Fresh state for a scenario. Every transport instance gets its own copy. */
export function buildState(scenario: ScenarioName): MockState {
  const c1 = clip(0x40, IDS.sessionReview, 1);
  const c2 = clip(0x41, IDS.sessionReview, 2, { captions_url: null });
  const clips: Clip[] = [c1, c2];
  const sessions: Session[] = [
    {
      id: IDS.sessionReview,
      dog_id: IDS.dogDraft,
      member_id: IDS.volunteer,
      owner_name: "Minji",
      situations: ["leash_walk", "new_person", "food_toys"],
      observed_on: DAY,
      status: "review",
      fail_code: null,
      created_at: T0,
      submitted_at: T0,
      review_ready_at: T0,
    },
    {
      id: IDS.sessionPublished,
      dog_id: IDS.dogPublished,
      member_id: IDS.staff,
      owner_name: "Sam",
      situations: ["other_dog", "children_cats"],
      observed_on: DAY,
      status: "review",
      fail_code: null,
      created_at: T0,
      submitted_at: T0,
      review_ready_at: T0,
    },
  ];
  const pubClip1 = clip(0x50, IDS.sessionPublished, 1);
  const pubClip2 = clip(0x51, IDS.sessionPublished, 2);
  clips.push(pubClip1, pubClip2);

  if (scenario === "failed_clip") {
    clips.push(
      clip(0x42, IDS.sessionReview, 3, {
        status: "failed",
        step: "transcribe",
        fail_code: "ai_failed",
        error: { cause: "Transcription failed. Try again.", retryable: true },
        media_url: null,
        captions_url: null,
        ready_at: null,
      }),
    );
  }
  if (scenario === "zero_fact_clip") {
    clips.push(clip(0x42, IDS.sessionReview, 3));
  }
  if (scenario === "merge_failed") {
    sessions.push({
      id: IDS.sessionMergeFailed,
      dog_id: IDS.dogDraft,
      member_id: IDS.volunteer,
      owner_name: "Minji",
      situations: ["alone_time"],
      observed_on: DAY,
      status: "failed",
      fail_code: "merge_failed",
      created_at: T0,
      submitted_at: T0,
      review_ready_at: null,
    });
    clips.push(clip(0x43, IDS.sessionMergeFailed, 1));
  }

  const isPb = scenario === "playback_required";
  const facts: Fact[] = [
    fact(
      0x60,
      IDS.dogDraft,
      IDS.sessionReview,
      "leash_walk",
      "Walked beside the handler on a loose leash down the hallway.",
      [evidence(0x70, c1.id, 12, 21)],
      isPb ? { can_confirm: true, blocked_reason: null } : {},
    ),
    fact(
      0x61,
      IDS.dogDraft,
      IDS.sessionReview,
      "new_person",
      "Walked up to the visitor and sniffed the offered hand, then sat.",
      [evidence(0x71, c2.id, 5, 12, false), evidence(0x72, c2.id, 30, 37, false)],
      {},
      [
        {
          code: "banned_word",
          severity: "warn",
          source: "rules",
          detail: "The word \"friendly\" states a trait. Describe what the dog did.",
        },
      ],
    ),
    fact(
      0x62,
      IDS.dogDraft,
      IDS.sessionReview,
      "food_toys",
      "Dropped the toy when asked, twice.",
      [evidence(0x73, c1.id, 40, 47)],
      {
        status: "confirmed",
        confirmed: CONFIRMED_BY,
        can_confirm: false,
        blocked_reason: "invalid_state",
      },
    ),
    // Published sample dog.
    fact(
      0x63,
      IDS.dogPublished,
      IDS.sessionPublished,
      "other_dog",
      "Walked past two dogs on leash without pulling.",
      [evidence(0x74, pubClip1.id, 8, 20)],
      { status: "confirmed", confirmed: CONFIRMED_BY, blocked_reason: "invalid_state" },
    ),
    fact(
      0x64,
      IDS.dogPublished,
      IDS.sessionPublished,
      "children_cats",
      "Stayed beside the handler while a child walked by at two metres.",
      [evidence(0x75, pubClip2.id, 3, 12)],
      { status: "confirmed", confirmed: CONFIRMED_BY, blocked_reason: "invalid_state" },
    ),
  ];

  return {
    members: [
      member(IDS.staff, MOCK_ACCOUNTS.staff.email, "Sam", "staff", true, MOCK_ACCOUNTS.staff.password),
      member(
        IDS.volunteer,
        MOCK_ACCOUNTS.volunteer.email,
        "Minji",
        "volunteer",
        false,
        MOCK_ACCOUNTS.volunteer.password,
      ),
    ],
    org: structuredClone(MOCK_ORG),
    dogs: [
      dog(IDS.dogDraft, "Biscuit", "medium", "draft", null),
      dog(IDS.dogPublished, "Juniper", "small", "published", MOCK_PUBLIC_SLUG),
    ],
    checklists: {
      [IDS.dogDraft]: {
        people_check: false,
        people_check_at: null,
        known_concerns: null,
        known_concerns_none: false,
      },
      [IDS.dogPublished]: {
        people_check: true,
        people_check_at: T0,
        known_concerns: "Pulls toward other dogs on leash.",
        known_concerns_none: false,
      },
    },
    sessions,
    clips,
    deletedClips: new Set(),
    facts,
    deletedFacts: new Set(),
    played: new Set(),
    nextId: 0x1000,
  };
}
