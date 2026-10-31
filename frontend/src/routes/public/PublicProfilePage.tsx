import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { isApiError } from "../../api/errors";
import { useApi } from "../../api/provider";
import type { PublicProfile } from "../../api/types";
import { AskBox } from "../../components/public/AskBox";
import { Banner } from "../../components/public/Banner";
import { ContactLinks } from "../../components/public/ContactLinks";
import { plural, SEX_LABEL } from "../../components/public/format";
import { PublicFactCard } from "../../components/public/PublicFactCard";
import { PublicPlayerProvider } from "../../components/public/PublicPlayerContext";
import { PublicPage } from "../../components/public/PublicPage";
import NotAvailablePage from "./NotAvailablePage";

type State =
  | { kind: "loading" }
  | { kind: "ok"; profile: PublicProfile }
  | { kind: "gone" }
  | { kind: "error"; text: string };

function loadError(e: unknown): string {
  if (!isApiError(e)) return "No connection. Check your network and try again.";
  if (e.code === "rate_limited") {
    const n = e.retryAfter;
    return n === null
      ? "Too many requests from your network. Try again in a moment."
      : `Too many requests from your network. Try again in ${n} ${plural(n, "second", "seconds")}.`;
  }
  return "Something went wrong on our side. Try again.";
}

function secs(n: number): string {
  return String(Math.round(n));
}

export default function PublicProfilePage() {
  const { slug = "" } = useParams();
  // A new slug starts from a clean loading state.
  return <ProfileScreen key={slug} slug={slug} />;
}

function ProfileScreen({ slug }: { slug: string }) {
  const api = useApi();
  const [state, setState] = useState<State>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let live = true;
    api
      .getPublicProfile(slug)
      .then((profile) => {
        if (live) setState({ kind: "ok", profile });
      })
      .catch((e: unknown) => {
        if (!live) return;
        if (isApiError(e) && e.code === "not_found") setState({ kind: "gone" });
        else setState({ kind: "error", text: loadError(e) });
      });
    return () => {
      live = false;
    };
  }, [api, slug, attempt]);

  const gone = useCallback(() => setState({ kind: "gone" }), []);

  useEffect(() => {
    if (state.kind !== "ok") return;
    const prev = document.title;
    document.title = `${state.profile.dog.name} - Watch Me!`;
    return () => {
      document.title = prev;
    };
  }, [state]);

  if (state.kind === "gone") return <NotAvailablePage />;

  if (state.kind === "loading") {
    return (
      <PublicPage>
        <Banner />
        <p role="status">Loading profile...</p>
      </PublicPage>
    );
  }

  if (state.kind === "error") {
    return (
      <PublicPage>
        <p role="alert" className="wm-error-text">
          {state.text}
        </p>
        <button
          type="button"
          className="wm-btn"
          onClick={() => {
            setState({ kind: "loading" });
            setAttempt((n) => n + 1);
          }}
        >
          Try again
        </button>
      </PublicPage>
    );
  }

  const p = state.profile;
  const { dog, org, coverage } = p;

  return (
    <PublicPlayerProvider>
      <PublicPage orgName={org.name}>
      <Banner bannerId={p.banner_id} />

      <header className="public-profile-head">
        {dog.photo_url ? (
          <img
            src={dog.photo_url}
            alt={`Photo of ${dog.name}`}
            width={96}
            height={96}
            className="wm-photo wm-photo--lg"
          />
        ) : (
          <div className="wm-photo wm-photo--lg public-photo-empty">
            No photo yet
          </div>
        )}
        <div>
          <h1>{dog.name}</h1>
          <p>{`${SEX_LABEL[dog.sex]}, ${dog.age_estimate}, ${dog.size}`}</p>
          <p>{dog.location}</p>
          <p className="wm-muted">{org.name}</p>
        </div>
      </header>

      <section aria-labelledby="coverage-h">
        <h2 id="coverage-h">Coverage</h2>
        <p>{`Clips in ${coverage.situations_covered} of ${coverage.situations_total} situations`}</p>
        <ul className="wm-list">
          {coverage.by_situation.map((s) => (
            <li key={s.situation}>
              <strong>{s.label}</strong>
              <div className="wm-muted">
                {s.clip_count === 0
                  ? "0 clips"
                  : `${s.clip_count} ${plural(s.clip_count, "clip", "clips")}, ${secs(s.filmed_s)} s filmed`}
              </div>
              {s.covered && <div className="wm-muted">{`${secs(s.confirmed_s)} s of it is used in facts`}</div>}
            </li>
          ))}
        </ul>
      </section>

      <nav aria-label="Jump to a section" className="public-nav">
        <a href="#facts">Facts</a>
        <a href="#not-observed">Not observed yet</a>
        <a href="#ask">Ask</a>
      </nav>

      <section aria-labelledby="concerns-h">
        <h2 id="concerns-h">Known concerns from the shelter</h2>
        {p.known_concerns.none_known ? (
          <>
            <p>None known.</p>
            <p>The shelter marked this field as none known.</p>
          </>
        ) : (
          <p style={{ whiteSpace: "pre-line" }}>{p.known_concerns.text}</p>
        )}
      </section>

      <section id="facts" aria-labelledby="facts-h">
        <h2 id="facts-h">Facts</h2>
        {p.facts_by_situation.length === 0 ? (
          <p>
            No facts are shown right now. The shelter may be updating this
            profile.
          </p>
        ) : (
          p.facts_by_situation.map((g) => (
            <div key={g.situation}>
              <h3>{g.label}</h3>
              <ul className="public-list">
                {g.facts.map((f) => (
                  <PublicFactCard key={f.id} fact={f} scope="facts" />
                ))}
              </ul>
            </div>
          ))
        )}
      </section>

      <section id="not-observed" aria-labelledby="no-h">
        <h2 id="no-h">Not observed yet</h2>
        {p.not_observed.length === 0 ? (
          <p>
            Every situation has at least one clip. The clips are still short
            samples.
          </p>
        ) : (
          <>
            <p>No clip shows these situations yet.</p>
            <ul className="public-list public-plain">
              {p.not_observed.map((s) => (
                <li key={s.situation}>{s.label}</li>
              ))}
            </ul>
          </>
        )}
      </section>

      <section aria-labelledby="contact-h">
        <h2 id="contact-h">Contact the shelter</h2>
        <p>{org.name}</p>
        <ContactLinks contact={p.contact} />
        <p>Applications happen with the shelter, not on this page.</p>
      </section>

      <AskBox
        slug={dog.slug}
        config={p.ask}
        contact={p.contact}
        onNotFound={gone}
      />

      <footer className="public-footer">
        <p>Questions use a cookie to count your hourly limit.</p>
        <p>
          <Link to="/terms">Terms</Link>
        </p>
      </footer>
      </PublicPage>
    </PublicPlayerProvider>
  );
}
