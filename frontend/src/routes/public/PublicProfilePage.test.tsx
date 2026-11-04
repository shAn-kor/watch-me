import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMockClient } from "../../api/mock";
import { fakeVideo, installFakeVideo } from "../../components/testing/fakeVideo";
import {
  SLUG,
  apiError,
  answer,
  clientWith,
  evidence,
  fact,
  profile,
  renderAt,
} from "../../components/public/publicTestKit";

const BANNER =
  "These clips are short samples. They are not a behavior or safety assessment. Meet the dog and talk to the shelter before adopting.";

beforeEach(() => {
  installFakeVideo();
  fakeVideo.reset();
});

async function shown(p = profile()) {
  const client = clientWith({ profile: p });
  const utils = renderAt(client, `/d/${SLUG}`);
  await screen.findByRole("heading", { level: 1, name: p.dog.name });
  return { client, ...utils };
}

describe("FE-PUB-01 banner is a constant", () => {
  it("renders the PRD text above the facts, whatever the API sends", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const bad = { ...profile(), banner_id: "other" } as unknown as ReturnType<typeof profile>;
    await shown(bad);
    const banner = screen.getByRole("complementary", { name: "Important notice" });
    expect(banner).toHaveTextContent(BANNER);
    expect(warn).toHaveBeenCalled();
    const factsHeading = screen.getByRole("heading", { level: 2, name: "Facts" });
    expect(
      banner.compareDocumentPosition(factsHeading) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    warn.mockRestore();
  });

  it("does not warn when banner_id matches, and tolerates a missing banner_id", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    await shown();
    expect(warn).not.toHaveBeenCalled();
    const p = profile() as Partial<ReturnType<typeof profile>>;
    delete p.banner_id;
    fakeVideo.reset();
    document.body.innerHTML = "";
    await shown(p as ReturnType<typeof profile>);
    expect(screen.getByRole("complementary", { name: "Important notice" })).toHaveTextContent(BANNER);
    warn.mockRestore();
  });

  it("shows the banner while loading", () => {
    const client = createMockClient();
    vi.spyOn(client, "getPublicProfile").mockReturnValue(new Promise(() => {}));
    renderAt(client, `/d/${SLUG}`);
    expect(screen.getByRole("complementary", { name: "Important notice" })).toHaveTextContent(BANNER);
    expect(screen.getByText("Loading profile...")).toBeInTheDocument();
  });

  it("shows the banner with no facts, and the empty-facts line", async () => {
    await shown(profile({ facts_by_situation: [] }));
    expect(screen.getByRole("complementary", { name: "Important notice" })).toBeInTheDocument();
    expect(
      screen.getByText("No facts are shown right now. The shelter may be updating this profile."),
    ).toBeInTheDocument();
  });
});

describe("FE-PUB-02 section order", () => {
  it("safety and concerns precede facts, questions and coverage", async () => {
    await shown();
    const order = [
      screen.getByRole("complementary", { name: "Important notice" }),
      screen.getByRole("heading", { level: 1, name: "Biscuit" }),
      screen.getByRole("heading", { level: 2, name: "Known concerns from the shelter" }),
      screen.getByRole("heading", { level: 2, name: "Facts" }),
      screen.getByRole("heading", { level: 2, name: "Ask about this dog" }),
      screen.getByRole("heading", { level: 2, name: "Coverage" }),
      screen.getByRole("heading", { level: 2, name: "Not observed yet" }),
      screen.getByRole("heading", { level: 2, name: "Contact the shelter" }),
    ];
    for (let i = 1; i < order.length; i++) {
      expect(
        order[i - 1]!.compareDocumentPosition(order[i]!) & Node.DOCUMENT_POSITION_FOLLOWING,
        `section ${i}`,
      ).toBeTruthy();
    }
  });

  it("header shows sex, age, size, location, org", async () => {
    await shown();
    expect(screen.getByText("Male, about 3 years, medium")).toBeInTheDocument();
    expect(screen.getByText("Portland, OR")).toBeInTheDocument();
    expect(screen.getAllByText("Maple Street Rescue").length).toBeGreaterThan(0);
    expect(screen.getByAltText("Photo of Biscuit")).toHaveAttribute("src", "/media/dogs/d1/photo.jpg");
  });

  it("shows a placeholder when there is no photo", async () => {
    const p = profile();
    p.dog.photo_url = null;
    await shown(p);
    expect(screen.getByText("No photo yet")).toBeInTheDocument();
  });
});

describe("FE-PUB-03 coverage text", () => {
  it("builds the line from numbers and lists per situation counts", async () => {
    await shown();
    expect(screen.getByText("Clips in 2 of 8 situations")).toBeInTheDocument();
    expect(screen.getByText("2 clips, 74 s filmed")).toBeInTheDocument();
    expect(screen.getByText("16 s of it is used in facts")).toBeInTheDocument();
    expect(screen.getByText("1 clip, 31 s filmed")).toBeInTheDocument();
    expect(screen.getByText("7 s of it is used in facts")).toBeInTheDocument();
    expect(screen.getAllByText("0 clips")).toHaveLength(6);
  });
});

describe("FE-PUB-04 fact item", () => {
  it("shows the labels and plays the range from its start on click", async () => {
    await shown();
    expect(screen.getByText("Walked beside the handler on a loose leash.")).toBeInTheDocument();
    expect(screen.getAllByText("1 clip, 9 s", { exact: false }).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Observed Oct 28, 2026").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Seen in clip", { exact: false }).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Confirmed by volunteer").length).toBeGreaterThan(0);
    expect(document.querySelector("video")).toBeNull();
    const btn = screen.getByRole("button", {
      name: "Play clip for: Walked beside the handler on a loose leash.",
    });
    expect(btn).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(btn);
    const v = document.querySelector("video")!;
    expect(v).toHaveAttribute("src", "/media/clip-f1.mp4");
    fireEvent.loadedMetadata(v);
    expect(v.currentTime).toBe(12);
    expect(btn).toHaveAttribute("aria-expanded", "true");
    expect(fakeVideo.play).toHaveBeenCalled();
  });

  it("one player at a time: opening a second card closes the first", async () => {
    await shown();
    fireEvent.click(screen.getByRole("button", { name: /Play clip for: Walked/ }));
    fireEvent.click(screen.getByRole("button", { name: /Play clip for: Looked/ }));
    expect(document.querySelectorAll("video")).toHaveLength(1);
    expect(document.querySelector("video")).toHaveAttribute("src", "/media/clip-f2.mp4");
  });

  it("Close collapses the card", async () => {
    await shown();
    fireEvent.click(screen.getByRole("button", { name: /Play clip for: Walked/ }));
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(document.querySelector("video")).toBeNull();
  });

  it("two ranges give Play range 1 and 2, each from its own start", async () => {
    const f = fact("f9", "Sniffed the toy.", {
      evidence: [evidence("c9", 5, 12), evidence("c9", 30, 37)],
    });
    await shown(
      profile({ facts_by_situation: [{ situation: "food_toys", label: "Food and toys", facts: [f] }] }),
    );
    fireEvent.click(screen.getByRole("button", { name: /Play range 2/ }));
    const v = document.querySelector("video")!;
    fireEvent.loadedMetadata(v);
    expect(v.currentTime).toBe(30);
  });

  it("captions track only when the API gave a URL", async () => {
    const f = fact("f8", "Rested.", { evidence: [evidence("c8", 1, 8, false)] });
    await shown(
      profile({ facts_by_situation: [{ situation: "indoors_rest", label: "Indoors and rest", facts: [f] }] }),
    );
    fireEvent.click(screen.getByRole("button", { name: /Play clip/ }));
    expect(document.querySelector("track")).toBeNull();
    expect(screen.getByText("No captions for this clip.")).toBeInTheDocument();
  });
});

describe("FE-PUB-05 known concerns", () => {
  it("shows the text", async () => {
    await shown();
    expect(screen.getByText("Pulls hard toward other dogs on leash.")).toBeInTheDocument();
  });
  it("shows none known", async () => {
    await shown(profile({ known_concerns: { none_known: true, text: null } }));
    expect(screen.getByText("None known.")).toBeInTheDocument();
    expect(screen.getByText("The shelter marked this field as none known.")).toBeInTheDocument();
  });
});

describe("FE-PUB-06 situation 8 notice", () => {
  it("shows the notice next to the fact", async () => {
    await shown();
    const card = screen.getByText("Looked at the shelter cat for 4 seconds.").closest("li")!;
    expect(
      within(card as HTMLElement).getByText("Ask the shelter about an in-person meeting."),
    ).toBeInTheDocument();
  });
});

describe("FE-PUB-07 not observed list", () => {
  it("lists every entry; count is 8 minus covered", async () => {
    await shown();
    const heading = screen.getByRole("heading", { level: 2, name: "Not observed yet" });
    const section = heading.closest("section")!;
    expect(within(section).getAllByRole("listitem")).toHaveLength(6);
    expect(within(section).getByText("Handling")).toBeInTheDocument();
  });
  it("empty list has its own sentence", async () => {
    await shown(profile({ not_observed: [] }));
    expect(
      screen.getByText("Every situation has at least one clip. The clips are still short samples."),
    ).toBeInTheDocument();
  });
});

describe("FE-PUB-08 contact block", () => {
  it("shows channels, opens link safely, has no form or submit", async () => {
    await shown();
    const section = screen.getByRole("heading", { level: 2, name: "Contact the shelter" }).closest("section")!;
    const link = within(section).getByRole("link", { name: "Open the shelter's page" });
    expect(link).toHaveAttribute("href", "https://shelter.example.org");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(within(section).getByRole("link", { name: "Email adopt@example.org" })).toHaveAttribute(
      "href",
      "mailto:adopt@example.org",
    );
    expect(within(section).queryByRole("button")).toBeNull();
    expect(section.querySelector("form")).toBeNull();
    expect(within(section).getByText("Applications happen with the shelter, not on this page.")).toBeInTheDocument();
  });
  it("email only shows only the email", async () => {
    await shown(profile({ contact: { url: null, email: "a@b.org", phone: null } }));
    expect(screen.queryByRole("link", { name: "Open the shelter's page" })).toBeNull();
    expect(screen.getByRole("link", { name: "Email a@b.org" })).toBeInTheDocument();
  });
});

describe("FE-PUB-09 hidden profile", () => {
  it("404 shows the not-available page with no dog data", async () => {
    const client = clientWith({ profile: apiError("not_found", 404) });
    renderAt(client, `/d/${SLUG}`);
    expect(await screen.findByRole("heading", { level: 1, name: "This profile is not available" })).toBeInTheDocument();
    expect(document.title).toBe("Profile not available");
    expect(screen.queryByText("Biscuit")).toBeNull();
    expect(screen.queryByText("Maple Street Rescue")).toBeNull();
    expect(screen.queryByRole("complementary", { name: "Important notice" })).toBeNull();
  });

  it("a 404 from Ask replaces the profile", async () => {
    const client = clientWith({ ask: apiError("not_found", 404) });
    renderAt(client, `/d/${SLUG}`);
    await screen.findByRole("heading", { level: 1, name: "Biscuit" });
    fireEvent.change(screen.getByLabelText("Ask about this dog"), { target: { value: "Does he pull?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByRole("heading", { level: 1, name: "This profile is not available" })).toBeInTheDocument();
    expect(screen.queryByText("Biscuit")).toBeNull();
  });

  it("the hidden_profile mock scenario reaches the page", async () => {
    renderAt(createMockClient({ scenario: "hidden_profile" }), "/d/k7m2q9x4tbwe");
    expect(await screen.findByRole("heading", { level: 1, name: "This profile is not available" })).toBeInTheDocument();
  });
});

describe("FE-PUB-10 narration and staff note", () => {
  it("labels both; staff note has no play control", async () => {
    const narr = fact("n1", "Said he loves walks.", {
      source: "narration",
      source_label: "Volunteer narration",
    });
    const staff = fact("s1", "Is crate trained.", { evidence: [] });
    await shown(
      profile({
        facts_by_situation: [
          { situation: "leash_walk", label: "Leash walk", facts: [narr] },
          { situation: "indoors_rest", label: "Indoors and rest", facts: [staff] },
        ],
      }),
    );
    expect(screen.getByText("The volunteer says this in the clip. The clip may not show it.")).toBeInTheDocument();
    expect(screen.getByText("Volunteer narration", { exact: false })).toBeInTheDocument();
    const staffCard = screen.getByText("Is crate trained.").closest("li") as HTMLElement;
    expect(within(staffCard).getByText("No clip.")).toBeInTheDocument();
    expect(within(staffCard).queryByRole("button")).toBeNull();
    expect(within(staffCard).getByText("Staff note", { exact: false })).toBeInTheDocument();
  });
});

describe("FE-PUB-11 no search or index page", () => {
  it("/ and unknown paths show the not-available page", async () => {
    for (const path of ["/", "/dogs", "/d"]) {
      const { unmount } = renderAt(createMockClient(), path);
      expect(
        await screen.findByRole("heading", { level: 1, name: "This profile is not available" }),
      ).toBeInTheDocument();
      expect(screen.queryByRole("list")).toBeNull();
      unmount();
    }
  });
});

describe("profile page errors and footer", () => {
  it("429 shows the wait and a Try again that reloads", async () => {
    const client = clientWith({ profile: apiError("rate_limited", 429, {}, 30) });
    renderAt(client, `/d/${SLUG}`);
    expect(
      await screen.findByText("Too many requests from your network. Try again in 30 seconds."),
    ).toBeInTheDocument();
    vi.mocked(client.getPublicProfile).mockResolvedValue(profile());
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Biscuit" })).toBeInTheDocument();
  });

  it("500 and network failures have their own text", async () => {
    const c1 = clientWith({ profile: apiError("internal_error", 500) });
    const r1 = renderAt(c1, `/d/${SLUG}`);
    expect(await screen.findByText("Something went wrong on our side. Try again.")).toBeInTheDocument();
    r1.unmount();
    const c2 = clientWith({ profile: new TypeError("fetch failed") });
    renderAt(c2, `/d/${SLUG}`);
    expect(await screen.findByText("No connection. Check your network and try again.")).toBeInTheDocument();
  });

  it("footer links to Terms and states the cookie line", async () => {
    await shown();
    expect(screen.getByRole("link", { name: "Terms" })).toHaveAttribute("href", "/terms");
    expect(screen.getByText("Questions use a cookie to count your hourly limit.")).toBeInTheDocument();
  });

  it("profile text is plain text, never HTML", async () => {
    await shown(
      profile({
        facts_by_situation: [
          {
            situation: "leash_walk",
            label: "Leash walk",
            facts: [fact("x", "<img src=x onerror=alert(1)>")],
          },
        ],
      }),
    );
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
    expect(document.querySelector("img[src='x']")).toBeNull();
  });
});

// keep helpers referenced
void act;
void waitFor;
void answer;

describe("FE-PUB-E2E-01 page structure and styling hooks", () => {
  it("uses the shared page frame so the creator stylesheet applies", async () => {
    const { container } = await shown();
    expect(container.querySelector(".wm-page.wm-public")).not.toBeNull();
    expect(container.querySelector(".wm-topbar")).not.toBeNull();
    expect(container.querySelector(".public-banner.wm-notice")).not.toBeNull();
  });

  it("ties the ask label to a textarea and puts the label above it", async () => {
    await shown();
    const box = screen.getByLabelText("Ask about this dog");
    expect(box.tagName).toBe("TEXTAREA");
    const label = document.querySelector('label[for="ask-q"]')!;
    expect(label).toHaveTextContent("Ask about this dog");
    expect(label.parentElement).toHaveClass("wm-field");
    expect(label.compareDocumentPosition(box) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("styles the play buttons as 44 px buttons", async () => {
    await shown();
    for (const b of screen.getAllByRole("button", { name: /^Play clip for:/ })) {
      expect(b).toHaveClass("wm-btn");
    }
  });
});

describe("FE-PUB-E2E-02 player controls", () => {
  it("opens the shared player with play, position, captions and sound controls", async () => {
    await shown();
    fireEvent.click(
      screen.getAllByRole("button", { name: /^Play clip for:/ })[0]!,
    );
    const video = document.querySelector("video")!;
    expect(video).not.toBeNull();
    expect(video).not.toHaveAttribute("controls");
    expect(document.querySelectorAll("video")).toHaveLength(1);
    expect(screen.getByRole("slider", { name: "Position" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Captions" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Sound" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /^(Loading clip|Play|Pause)$/ }),
    ).toBeInTheDocument();
  });
});

describe("E2E 4 public ranges in time order", () => {
  it("lists ranges of a fact by start time", async () => {
    const f = fact("fx", "Moved between a person's feet.", {
      evidence: [evidence("clip-a", 13, 14), evidence("clip-a", 2, 4)],
    });
    const p = profile({
      facts_by_situation: [{ situation: "new_person", label: "Meeting a new person", facts: [f] }],
    });
    await shown(p);
    const buttons = screen.getAllByRole("button", { name: /^Play range \d for:/ });
    expect(buttons).toHaveLength(2);
    fireEvent.click(buttons[0]!);
    expect(document.querySelector("video")).toHaveAttribute("src", "/media/clip-a.mp4");
    expect(screen.getByText(/0:02 - 0:04/)).toBeInTheDocument();
  });
});
