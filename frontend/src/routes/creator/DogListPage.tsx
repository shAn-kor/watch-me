import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useApi } from "../../api/provider";
import type { DogListItem } from "../../api/types";
import { DogStatusChip } from "../../components/creator/Chips";
import { ErrorNotice } from "../../components/creator/errors";
import { Loading, Screen } from "../../components/creator/ui";
import { useEnsureAuth } from "../../state/AuthProvider";

function countsLine(item: DogListItem): string | null {
  const { draft_facts, confirmed_facts, clips, sessions_in_review } = item.counts;
  if (draft_facts + confirmed_facts > 0 || clips > 0) {
    return `${draft_facts} drafts to review - ${confirmed_facts} confirmed`;
  }
  if (sessions_in_review > 0) return null;
  return null;
}

function DogRow({ item }: { item: DogListItem }) {
  const { dog, coverage, counts } = item;
  const coverageText = `Clips in ${coverage.situations_covered} of 8 situations`;
  const line = countsLine(item);
  const ready = counts.sessions_in_review > 0 && counts.draft_facts === 0;
  const statusText = dog.status;
  const label = [
    dog.name,
    statusText,
    coverageText.toLowerCase().replace(/^clips/, "clips"),
    line && counts.draft_facts > 0 ? `${counts.draft_facts} drafts to review` : null,
  ]
    .filter(Boolean)
    .join(", ");
  return (
    <li>
      <Link to={`/app/dogs/${dog.id}`} className="wm-dog-link" aria-label={label}>
        {dog.photo_url ? (
          <img src={dog.photo_url} alt="" className="wm-photo" />
        ) : (
          <div className="wm-photo" aria-hidden="true" />
        )}
        <div>
          <div className="wm-row">
            <span className="wm-strong">{dog.name}</span>
            <DogStatusChip status={dog.status} />
          </div>
          <div className="wm-muted">{coverageText}</div>
          {line ? <div className="wm-muted">{line}</div> : null}
          {ready ? <div className="wm-muted">Session ready to review</div> : null}
        </div>
      </Link>
    </li>
  );
}

/** S3 Dog list (05 section 5). */
export default function DogListPage() {
  const api = useApi();
  const auth = useEnsureAuth();
  const q = useQuery({
    queryKey: ["dogs"],
    queryFn: () => api.listDogs(),
    enabled: auth.status === "authed",
  });
  const title = auth.org?.name ?? "Dogs";
  const needsConsent = auth.member !== null && !auth.member.consented_at;

  return (
    <Screen title={title}>
      {needsConsent ? (
        <div className="wm-notice">
          <p>Accept the consent notice before you add clips.</p>
          <p>
            <Link to="/app/consent">Open consent notice</Link>
          </p>
        </div>
      ) : null}
      <div className="wm-row wm-row--between">
        <h1>Dogs</h1>
        {q.data && q.data.dogs.length > 0 ? (
          <>
            <span className="wm-muted">({q.data.dogs.length})</span>
            <Link to="/app/dogs/new" className="wm-btn">
              Add dog
            </Link>
          </>
        ) : null}
      </div>
      {q.isError ? (
        <ErrorNotice error={q.error} onRetry={() => void q.refetch()} />
      ) : q.data ? (
        q.data.dogs.length === 0 ? (
          <div className="wm-stack">
            <p className="wm-strong">No dogs yet.</p>
            <p>Add the first dog to start a profile.</p>
            <Link to="/app/dogs/new" className="wm-btn">
              Add dog
            </Link>
          </div>
        ) : (
          <ul className="wm-list" aria-label="Dogs">
            {q.data.dogs.map((d) => (
              <DogRow key={d.dog.id} item={d} />
            ))}
          </ul>
        )
      ) : (
        <Loading text="Loading dogs..." onRetry={() => void q.refetch()} />
      )}
    </Screen>
  );
}
