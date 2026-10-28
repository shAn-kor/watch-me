import { useEffect, useRef, useState } from "react";
import { useApi } from "../../api/provider";
import { isApiError } from "../../api/errors";
import type { Contact, PublicProfile, QaAnswer } from "../../api/types";
import { ContactLinks } from "./ContactLinks";
import { plural } from "./format";
import { PublicFactCard } from "./PublicFactCard";

const MIN_CHARS = 3;

interface Failure {
  text: string;
  waitS?: number;
  pause?: boolean;
}

function failureOf(e: unknown, limitPerHour: number): Failure {
  if (!isApiError(e))
    return { text: "No connection. Your question was not sent." };
  switch (e.code) {
    case "rate_limited": {
      const wait = e.retryAfter ?? 3600;
      const m = Math.max(1, Math.ceil(wait / 60));
      return {
        text: `You have used all ${limitPerHour} questions for this hour. Try again in ${m} ${plural(m, "minute", "minutes")}.`,
        waitS: wait,
      };
    }
    case "qa_cost_cap_reached": {
      const base =
        "Questions are paused for today. The facts on this page are still here.";
      if (e.retryAfter === null) return { text: base, pause: true };
      const h = Math.max(1, Math.ceil(e.retryAfter / 3600));
      return {
        text: `${base} Questions open again in about ${h} ${plural(h, "hour", "hours")}.`,
        pause: true,
      };
    }
    case "qa_unavailable":
      return {
        text: "We could not look up an answer. Nothing was guessed. Try again, or contact the shelter.",
      };
    case "question_too_short":
      return { text: "Type at least 3 characters." };
    case "validation_error":
      return { text: "Keep your question to 300 characters or fewer." };
    case "malformed_request":
    case "unsupported_media_type":
      return {
        text: "The question could not be sent. Reload the page and try again.",
      };
    default:
      return { text: "Something went wrong on our side. Try again." };
  }
}

export interface AskBoxProps {
  slug: string;
  config: PublicProfile["ask"];
  contact: Contact;
  /** The shelter took the profile down: the page swaps to S10. */
  onNotFound: () => void;
}

/** Ask box and answer block (QA-1, QA-2, QA-4). The model's words render as text only. */
export function AskBox({ slug, config, onNotFound }: AskBoxProps) {
  const api = useApi();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [answer, setAnswer] = useState<QaAnswer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [until, setUntil] = useState<number | null>(null);
  const [paused, setPaused] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (until === null) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [until]);

  useEffect(() => {
    if (answer) headingRef.current?.focus();
  }, [answer]);

  if (!config.enabled) {
    return (
      <section id="ask" aria-labelledby="ask-h">
        <h2 id="ask-h">Ask about this dog</h2>
        <p>Questions are turned off for this profile.</p>
      </section>
    );
  }

  const trimmed = text.trim().length;
  const counting = until !== null && now < until;
  const disabled =
    busy ||
    paused ||
    counting ||
    trimmed < MIN_CHARS ||
    trimmed > config.max_question_chars;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (disabled) return;
    setBusy(true);
    setError(null);
    try {
      setAnswer(await api.ask(slug, text.trim()));
    } catch (err) {
      if (isApiError(err) && err.code === "not_found") {
        onNotFound();
        return;
      }
      const f = failureOf(err, config.limit_per_hour);
      setError(f.text);
      if (f.waitS !== undefined) {
        const t = Date.now();
        setNow(t);
        setUntil(t + f.waitS * 1000);
      }
      if (f.pause) setPaused(true);
    } finally {
      setBusy(false);
    }
  };

  const remaining = answer?.limits.remaining_this_hour;

  return (
    <section id="ask" aria-labelledby="ask-h">
      <h2 id="ask-h">Ask about this dog</h2>
      <p>Answers use only confirmed facts on this page.</p>
      <form onSubmit={submit}>
        <label htmlFor="ask-q">Ask about this dog</label>
        <textarea
          id="ask-q"
          rows={3}
          value={text}
          readOnly={busy}
          placeholder="For example: Does he pull on the leash?"
          onChange={(e) => setText(e.target.value)}
        />
        <p>
          <span>
            {text.length} / {config.max_question_chars}
          </span>{" "}
          <span>
            {remaining === undefined
              ? `Up to ${config.limit_per_hour} questions per hour.`
              : `${remaining} ${plural(remaining, "question", "questions")} left this hour.`}
          </span>
        </p>
        <button type="submit" disabled={disabled}>
          {busy ? "Asking..." : "Ask"}
        </button>
      </form>
      {error && <p role="alert">{error}</p>}
      <div role="region" aria-label="Answer" aria-live="polite">
        {answer && (
          <div>
            <h3 ref={headingRef} tabIndex={-1}>
              {answer.heading}
            </h3>
            {answer.hint && <p>{answer.hint}</p>}
            {answer.outcome === "answered" && (
              <ul>
                {answer.lines.map((l) => (
                  <PublicFactCard
                    key={l.fact_id}
                    scope="ask"
                    situationLabel={l.situation_label}
                    fact={{
                      id: l.fact_id,
                      behavior: l.text,
                      source: l.evidence.length ? "clip" : "staff_note",
                      source_label: l.source_label,
                      observed_on: l.observed_on,
                      confirmed_by_label: l.confirmed_by_label,
                      clip_length: l.clip_length,
                      notice: l.notice,
                      evidence: l.evidence,
                    }}
                  />
                ))}
              </ul>
            )}
            {answer.outcome === "not_observed" && (
              <a
                href="#not-observed"
                onClick={(e) => {
                  const el = document.getElementById("not-observed");
                  if (el) {
                    e.preventDefault();
                    el.scrollIntoView?.();
                  }
                }}
              >
                See what has not been filmed
              </a>
            )}
            {answer.outcome === "health_redirect" && answer.contact && (
              <ContactLinks contact={answer.contact} />
            )}
          </div>
        )}
      </div>
    </section>
  );
}
