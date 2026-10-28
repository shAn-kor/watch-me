import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiProvider } from "../../api/provider";
import { fakeVideo, installFakeVideo } from "../testing/fakeVideo";
import { AskBox } from "./AskBox";
import { PublicPlayerProvider } from "./PublicPlayerContext";
import { SLUG, answer, apiError, clientWith, line, profile } from "./publicTestKit";
import type { ApiClient } from "../../api/client";
import type { QaAnswer } from "../../api/types";

beforeEach(() => {
  installFakeVideo();
  fakeVideo.reset();
});
afterEach(() => {
  vi.useRealTimers();
});

function mount(client: ApiClient, onNotFound = vi.fn()) {
  const p = profile();
  const utils = render(
    <ApiProvider client={client}>
      <PublicPlayerProvider>
        <AskBox slug={SLUG} config={p.ask} contact={p.contact} onNotFound={onNotFound} />
      </PublicPlayerProvider>
    </ApiProvider>,
  );
  return { ...utils, onNotFound };
}

function type(text: string) {
  fireEvent.change(screen.getByLabelText("Ask about this dog"), { target: { value: text } });
}
async function submit(text = "Does he pull on the leash?") {
  type(text);
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
  });
}

describe("FE-ASK-01 answers as plain text", () => {
  it("renders hostile line text as text", async () => {
    const hostile = "<img src=x onerror=alert(1)>";
    mount(clientWith({ ask: answer({ lines: [line("f1", hostile)] }) }));
    await submit();
    const region = screen.getByRole("region", { name: "Answer" });
    expect(within(region).getByText(hostile)).toBeInTheDocument();
    expect(region.querySelector("img")).toBeNull();
    expect(document.querySelector("img")).toBeNull();
  });
});

describe("FE-ASK-02 outcomes", () => {
  it("answered: heading, lines, no added words", async () => {
    mount(clientWith({ ask: answer() }));
    await submit();
    const region = screen.getByRole("region", { name: "Answer" });
    expect(region).toHaveAttribute("aria-live", "polite");
    const h = within(region).getByRole("heading", { name: "Here is what has been filmed:" });
    expect(h).toHaveFocus();
    expect(within(region).getByText("Walked beside the handler on a loose leash.")).toBeInTheDocument();
    expect(within(region).getByText("Leash walk")).toBeInTheDocument();
  });

  it("not_observed: heading, hint and the jump link", async () => {
    const a: QaAnswer = answer({
      outcome: "not_observed",
      heading: "Not observed yet.",
      hint: "No confirmed fact covers this. Ask the shelter.",
      lines: [],
      cited_fact_ids: [],
    });
    mount(clientWith({ ask: a }));
    await submit();
    expect(screen.getByRole("heading", { name: "Not observed yet." })).toBeInTheDocument();
    expect(screen.getByText("No confirmed fact covers this. Ask the shelter.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See what has not been filmed" })).toHaveAttribute(
      "href",
      "#not-observed",
    );
  });

  it("health_redirect: vet text and contact", async () => {
    const a: QaAnswer = answer({
      outcome: "health_redirect",
      heading: "Ask the shelter's vet.",
      hint: "Health questions are answered by the shelter.",
      lines: [],
      cited_fact_ids: [],
      contact: { url: null, email: "vet@example.org", phone: "+1 555 0100" },
    });
    mount(clientWith({ ask: a }));
    await submit("Is he vaccinated?");
    expect(screen.getByRole("heading", { name: "Ask the shelter's vet." })).toBeInTheDocument();
    expect(screen.getByText("Health questions are answered by the shelter.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Email vet@example.org" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Call +1 555 0100" })).toHaveAttribute("href", "tel:+1 555 0100");
  });

  it("only the latest result shows, and the text stays in the field", async () => {
    const client = clientWith({ ask: answer() });
    mount(client);
    await submit("first question");
    vi.mocked(client.ask).mockResolvedValue(
      answer({ heading: "Second heading", lines: [line("f2", "Second line.")] }),
    );
    await submit("second question");
    expect(screen.queryByText("Walked beside the handler on a loose leash.")).toBeNull();
    expect(screen.getByText("Second line.")).toBeInTheDocument();
    expect(screen.getByLabelText("Ask about this dog")).toHaveValue("second question");
  });

  it("sends the trimmed question for the slug", async () => {
    const client = clientWith({ ask: answer() });
    mount(client);
    await submit("  Does he pull?  ");
    expect(client.ask).toHaveBeenCalledWith(SLUG, "Does he pull?");
  });
});

describe("FE-ASK-03 tap line plays range", () => {
  it("plays the evidence range in the shared player", async () => {
    mount(clientWith({ ask: answer() }));
    await submit();
    fireEvent.click(screen.getByRole("button", { name: /Play clip for: Walked/ }));
    const v = document.querySelector("video")!;
    expect(v).toHaveAttribute("src", "/media/clip-f1.mp4");
    fireEvent.loadedMetadata(v);
    expect(v.currentTime).toBe(12);
  });
});

describe("FE-ASK-04 limits and errors", () => {
  it("429 shows minutes and disables Ask until the countdown ends", async () => {
    vi.useFakeTimers();
    mount(clientWith({ ask: apiError("rate_limited", 429, { scope: "ip" }, 120) }));
    await submit();
    expect(
      screen.getByText("You have used all 10 questions for this hour. Try again in 2 minutes."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
    await act(async () => {
      vi.advanceTimersByTime(119_000);
    });
    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
    await act(async () => {
      vi.advanceTimersByTime(2_000);
    });
    expect(screen.getByRole("button", { name: "Ask" })).toBeEnabled();
  });

  it("cookie scope shows the same hourly message", async () => {
    mount(clientWith({ ask: apiError("rate_limited", 429, { scope: "cookie" }, 3000) }));
    await submit();
    expect(
      screen.getByText("You have used all 10 questions for this hour. Try again in 50 minutes."),
    ).toBeInTheDocument();
  });

  it("cost cap pauses Ask for the page", async () => {
    mount(clientWith({ ask: apiError("qa_cost_cap_reached", 503, {}, 7200) }));
    await submit();
    expect(
      screen.getByText(
        "Questions are paused for today. The facts on this page are still here. Questions open again in about 2 hours.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
  });

  it.each([
    ["qa_unavailable", 503, "We could not look up an answer. Nothing was guessed. Try again, or contact the shelter."],
    ["question_too_short", 422, "Type at least 3 characters."],
    ["validation_error", 422, "Keep your question to 300 characters or fewer."],
    ["internal_error", 500, "Something went wrong on our side. Try again."],
    ["malformed_request", 400, "The question could not be sent. Reload the page and try again."],
    ["unsupported_media_type", 415, "The question could not be sent. Reload the page and try again."],
  ] as const)("%s shows its own message and no answer", async (code, status, text) => {
    mount(clientWith({ ask: apiError(code, status) }));
    await submit();
    expect(screen.getByText(text)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /filmed/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Ask" })).toBeEnabled();
  });

  it("network failure says the question was not sent", async () => {
    mount(clientWith({ ask: new TypeError("fetch failed") }));
    await submit();
    expect(screen.getByText("No connection. Your question was not sent.")).toBeInTheDocument();
  });

  it("404 calls onNotFound", async () => {
    const { onNotFound } = mount(clientWith({ ask: apiError("not_found", 404) }));
    await submit();
    expect(onNotFound).toHaveBeenCalledTimes(1);
  });

  it("mock scenarios rate_limited and cost_cap are reachable", async () => {
    const { createMockClient } = await import("../../api/mock");
    const { unmount } = mount(createMockClient({ scenario: "rate_limited" }));
    await submit();
    expect(await screen.findByText(/Try again in 1 minutes?\./)).toBeInTheDocument();
    unmount();
    mount(createMockClient({ scenario: "cost_cap" }));
    await submit("How is he with food?");
    expect(await screen.findByText(/Questions are paused for today/)).toBeInTheDocument();
  });

  it("shows Asking... and a read-only field while waiting", async () => {
    const client = clientWith({ ask: answer() });
    vi.mocked(client.ask).mockReturnValue(new Promise(() => {}));
    mount(client);
    type("Does he pull?");
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByRole("button", { name: "Asking..." })).toBeDisabled();
    expect(screen.getByLabelText("Ask about this dog")).toHaveAttribute("readonly");
  });
});

describe("FE-ASK-05 input rules", () => {
  it("disabled under 3 trimmed chars, enabled at 3, disabled over 300", () => {
    mount(clientWith({}));
    const ask = screen.getByRole("button", { name: "Ask" });
    expect(ask).toBeDisabled();
    type("ab");
    expect(ask).toBeDisabled();
    type("  ab  ");
    expect(ask).toBeDisabled();
    type("abc");
    expect(ask).toBeEnabled();
    expect(screen.getByText("3 / 300")).toBeInTheDocument();
    type("a".repeat(300));
    expect(ask).toBeEnabled();
    type("a".repeat(301));
    expect(screen.getByText("301 / 300")).toBeInTheDocument();
    expect(ask).toBeDisabled();
  });

  it("shows the limit before and the remaining count after the first answer", async () => {
    mount(clientWith({ ask: answer({ limits: { remaining_this_hour: 8 } }) }));
    expect(screen.getByText("Up to 10 questions per hour.")).toBeInTheDocument();
    await submit();
    expect(screen.getByText("8 questions left this hour.")).toBeInTheDocument();
  });

  it("placeholder is the example question", () => {
    mount(clientWith({}));
    expect(screen.getByPlaceholderText("For example: Does he pull on the leash?")).toBeInTheDocument();
  });

  it("ask.enabled=false hides the box", () => {
    const p = profile();
    render(
      <ApiProvider client={clientWith({})}>
        <PublicPlayerProvider>
          <AskBox slug={SLUG} config={{ ...p.ask, enabled: false }} contact={p.contact} onNotFound={() => {}} />
        </PublicPlayerProvider>
      </ApiProvider>,
    );
    expect(screen.getByText("Questions are turned off for this profile.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ask" })).toBeNull();
  });
});
