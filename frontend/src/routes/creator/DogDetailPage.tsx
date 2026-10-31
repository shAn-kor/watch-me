import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { isApiError } from "../../api/errors";
import { useApi } from "../../api/provider";
import type { DogDetailResponse, Fact, SessionSummary } from "../../api/types";
import {
  DogStatusChip,
  FactStatusChip,
  OriginChip,
} from "../../components/creator/Chips";
import { ErrorNotice } from "../../components/creator/errors";
import {
  formatDay,
  SEX_LABEL,
  SIZE_LABEL,
} from "../../components/creator/format";
import { PublishPanel } from "../../components/creator/PublishPanel";
import { BlockedButton, Loading, Screen } from "../../components/creator/ui";
import { SITUATIONS } from "../../lib/constants";
import { useEnsureAuth } from "../../state/AuthProvider";

/** A session in review whose drafts are all confirmed is done, not "ready to review". */
function allConfirmed(s: SessionSummary, confirmed: number): boolean {
  return s.status === "review" && s.draft_fact_count === 0 && confirmed > 0;
}

function sessionStatus(s: SessionSummary, confirmed: number): string {
  switch (s.status) {
    case "processing":
      return `Processing - ${s.ready_clip_count} of ${s.clip_count} clips ready`;
    case "failed":
      return `Failed - ${
        s.fail_code === "merge_failed"
          ? "We could not finish drafting facts."
          : "No clip could be processed."
      }`;
    case "review":
      return allConfirmed(s, confirmed)
        ? "All facts confirmed"
        : "Ready to review";
    default:
      return `Not submitted - ${s.clip_count} ${s.clip_count === 1 ? "clip" : "clips"}`;
  }
}

function SessionRow({ s, confirmed }: { s: SessionSummary; confirmed: number }) {
  return (
    <li>
      <p className="wm-strong">
        {formatDay(s.observed_on)} - {s.owner_name}
      </p>
      <p>{sessionStatus(s, confirmed)}</p>
      {s.status === "review" && !allConfirmed(s, confirmed) ? (
        <p className="wm-muted">{s.draft_fact_count} drafts</p>
      ) : null}
      <Link
        to={
          s.status === "review"
            ? `/app/sessions/${s.id}/review`
            : `/app/sessions/${s.id}`
        }
        className="wm-btn wm-btn--secondary"
      >
        {s.status === "review" ? "Review facts" : "Open"}
      </Link>
    </li>
  );
}

function FactRow({ f }: { f: Fact }) {
  const flagged = f.flags.some((x) => x.severity === "warn");
  return (
    <li>
      <p>{f.behavior}</p>
      <div className="wm-row">
        <FactStatusChip status={f.status} />
        <OriginChip origin={f.origin} />
        {flagged ? (
          <span className="wm-chip wm-chip--plain">Wording flag</span>
        ) : null}
        <span className="wm-muted">{f.clip_length.label}</span>
      </div>
    </li>
  );
}

function Facts({ data }: { data: DogDetailResponse }) {
  const groups = SITUATIONS.map((s) => ({
    ...s,
    facts: data.facts.filter((f) => f.situation === s.code),
  })).filter((g) => g.facts.length > 0);
  return (
    <section aria-labelledby="facts-h">
      <div className="wm-row wm-row--between">
        <h2 id="facts-h">Facts ({data.facts.length})</h2>
        {data.facts.length > 0 ? (
          <Link
            to={`/app/dogs/${data.dog.id}/review`}
            className="wm-btn wm-btn--secondary"
          >
            Review facts
          </Link>
        ) : null}
      </div>
      {groups.length === 0 ? <p>No facts yet.</p> : null}
      {groups.map((g) => (
        <div key={g.code}>
          <h3>{g.label}</h3>
          <ul className="wm-list">
            {g.facts.map((f) => (
              <FactRow key={f.id} f={f} />
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}

/** S5 Dog detail (05 section 5). */
export default function DogDetailPage() {
  const { dogId = "" } = useParams();
  const api = useApi();
  const auth = useEnsureAuth();
  const q = useQuery({
    queryKey: ["dog", dogId],
    queryFn: () => api.getDog(dogId),
    enabled: auth.status === "authed",
    refetchInterval: (query) =>
      query.state.data?.sessions.some((s) => s.status === "processing")
        ? 5000
        : false,
  });

  if (q.isError && !q.data) {
    return (
      <Screen title="Dog" backTo="/app/dogs">
        <ErrorNotice
          error={q.error}
          table={{
            not_found: "This dog was not found. It may have been deleted.",
          }}
          backLink={isApiError(q.error) && q.error.code === "not_found"}
          onRetry={
            isApiError(q.error) && q.error.code === "not_found"
              ? undefined
              : () => void q.refetch()
          }
        />
      </Screen>
    );
  }
  if (!q.data || !auth.member) {
    return (
      <Screen title="Dog" backTo="/app/dogs">
        <Loading text="Loading dog..." onRetry={() => void q.refetch()} />
      </Screen>
    );
  }

  const data = q.data;
  const { dog, coverage } = data;
  const isStaff = auth.member.role === "staff";
  const consented = Boolean(auth.member.consented_at);

  let reason: string | null = null;
  if (dog.status === "published")
    reason = "Unpublish this dog before you add clips.";
  else if (dog.status === "adopted")
    reason = "This dog is marked as adopted. Reopen it to add clips.";
  else if (!consented) reason = "Accept the consent notice to add clips.";

  const details = [
    SEX_LABEL[dog.sex],
    dog.age_estimate,
    SIZE_LABEL[dog.size].toLowerCase(),
  ].join(", ");

  return (
    <Screen title="Dog" backTo="/app/dogs">
      <div className="wm-dog-link">
        {dog.photo_url ? (
          <img src={dog.photo_url} alt="" className="wm-photo wm-photo--lg" />
        ) : (
          <div className="wm-photo wm-photo--lg" aria-hidden="true" />
        )}
        <div>
          <h1>{dog.name}</h1>
          <DogStatusChip status={dog.status} />
          <p>{details}</p>
          {dog.location ? <p>{dog.location}</p> : null}
          <Link
            to={`/app/dogs/${dog.id}/edit`}
            className="wm-btn wm-btn--secondary"
          >
            Edit
          </Link>
        </div>
      </div>

      <section aria-labelledby="coverage-h">
        <h2 id="coverage-h">Coverage</h2>
        <p>{`Clips in ${coverage.situations_covered} of ${coverage.situations_total} situations`}</p>
        <table className="wm-table" aria-label="Coverage">
          <tbody>
            {coverage.by_situation.map((c) => (
              <tr key={c.situation}>
                <th scope="row">{c.label}</th>
                <td>
                  {c.clip_count === 0
                    ? "Not observed yet"
                    : `${c.clip_count} ${c.clip_count === 1 ? "clip" : "clips"}, ${Math.round(c.filmed_s)} s`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <div className="wm-stack" style={{ margin: "16px 0" }}>
        {reason === null ? (
          <Link to={`/app/dogs/${dog.id}/sessions/new`} className="wm-btn">
            New session
          </Link>
        ) : (
          <>
            <BlockedButton
              blocked
              describedBy="new-session-reason"
              onClick={() => undefined}
            >
              New session
            </BlockedButton>
            <p id="new-session-reason" className="wm-muted">
              {reason}
            </p>
          </>
        )}
      </div>

      <section aria-labelledby="sessions-h">
        <h2 id="sessions-h">Sessions</h2>
        {data.sessions.length === 0 ? (
          <p>No sessions yet. Start one to add clips.</p>
        ) : (
          <ul className="wm-list">
            {data.sessions.map((s) => (
              <SessionRow
                key={s.id}
                s={s}
                confirmed={
                  data.facts.filter(
                    (f) => f.session_id === s.id && f.status === "confirmed",
                  ).length
                }
              />
            ))}
          </ul>
        )}
      </section>

      <Facts data={data} />

      <PublishPanel key={dog.id} data={data} isStaff={isStaff} />
    </Screen>
  );
}
