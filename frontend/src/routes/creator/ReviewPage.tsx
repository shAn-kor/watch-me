import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { isApiError } from "../../api/errors";
import { useApi } from "../../api/provider";
import type { Clip, DogDetailResponse, Fact, Session } from "../../api/types";
import { ConfirmDialog } from "../../components/creator/Dialog";
import { ErrorNotice } from "../../components/creator/errors";
import { FactCard } from "../../components/creator/FactCard";
import {
  AddFactSheet,
  EditFactSheet,
} from "../../components/creator/FactSheets";
import { useToast } from "../../components/creator/Toast";
import { BlockedButton, Loading, Screen } from "../../components/creator/ui";
import { useEnsureAuth } from "../../state/AuthProvider";

type Filter = "review" | "confirmed" | "all";

interface Loaded {
  dogId: string;
  facts: Fact[];
  clips: Clip[];
  /** Session owner by session id, for the edit and delete rule. */
  owners: Record<string, string>;
  session: Session | null;
  dogDetail: DogDetailResponse | null;
}

/** S8 Review facts (05 section 5): session scope and dog scope. */
export default function ReviewPage() {
  const params = useParams();
  const sessionId = params.sessionId;
  const dogParam = params.dogId;
  const scope = sessionId ? "session" : "dog";
  const scopeId = sessionId ?? dogParam ?? "";

  const api = useApi();
  const auth = useEnsureAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const authed = auth.status === "authed" && auth.member !== null;

  const [filter, setFilter] = useState<Filter>("review");
  const [editing, setEditing] = useState<Fact | null>(null);
  const [deleting, setDeleting] = useState<Fact | null>(null);
  const [adding, setAdding] = useState<{ clipId?: string } | null>(null);
  const [live, setLive] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);
  const focusAfter = useRef<string | null>(null);

  const q = useQuery({
    queryKey: ["review", scope, scopeId],
    enabled: authed,
    queryFn: async (): Promise<Loaded> => {
      if (scope === "session") {
        const s = await api.getSession(scopeId);
        let dogDetail: DogDetailResponse | null;
        try {
          dogDetail = await api.getDog(s.session.dog_id);
        } catch {
          dogDetail = null;
        }
        return {
          dogId: s.session.dog_id,
          facts: s.facts,
          clips: s.clips,
          owners: { [s.session.id]: s.session.member_id },
          session: s.session,
          dogDetail,
        };
      }
      const d = await api.getDog(scopeId);
      return {
        dogId: d.dog.id,
        facts: d.facts,
        clips: d.clips,
        owners: Object.fromEntries(d.sessions.map((x) => [x.id, x.member_id])),
        session: null,
        dogDetail: d,
      };
    },
  });

  const reload = () => {
    void qc.invalidateQueries({ queryKey: ["review", scope, scopeId] });
    void qc.invalidateQueries({ queryKey: ["dog"] });
  };

  const data = q.data;
  const draftsNow = data
    ? data.facts.filter((f) => f.status === "draft").length
    : 0;

  // Move focus to the heading of the card that took the removed card's place.
  useEffect(() => {
    const id = focusAfter.current;
    if (!id) return;
    focusAfter.current = null;
    document.getElementById(`fact-h-${id}`)?.focus();
  });

  if (!authed || (!data && !q.isError)) {
    return (
      <Screen title="Review" backTo="/app/dogs">
        <Loading text="Loading facts..." onRetry={() => void q.refetch()} />
      </Screen>
    );
  }
  if (q.isError && !data) {
    const missing = isApiError(q.error) && q.error.code === "not_found";
    return (
      <Screen title="Review" backTo="/app/dogs">
        <ErrorNotice
          error={q.error}
          table={{
            not_found:
              scope === "session"
                ? "This session was not found. It may have been deleted."
                : "This dog was not found. It may have been deleted.",
          }}
          backLink={missing}
          onRetry={missing ? undefined : () => void q.refetch()}
        />
      </Screen>
    );
  }
  if (!data) return null;
  const member = auth.member!;

  if (data.session && data.session.status !== "review") {
    return <Navigate to={`/app/sessions/${data.session.id}`} replace />;
  }

  const dog = data.dogDetail?.dog ?? null;
  const checklist = data.dogDetail?.checklist ?? null;
  const isStaff = member.role === "staff";
  const consented = Boolean(member.consented_at);
  const wordingMode = auth.limits.wording_check;
  const dogPublished = dog?.status === "published";

  const drafts = data.facts.filter((f) => f.status === "draft");
  const confirmed = data.facts.filter((f) => f.status === "confirmed");
  const shown =
    filter === "review"
      ? drafts
      : filter === "confirmed"
        ? confirmed
        : data.facts;

  const ownSession = (sessionId: string | null) =>
    sessionId !== null && data.owners[sessionId] === member.id;
  const canEdit = (f: Fact) =>
    isStaff || ownSession(f.session_id) || f.created_by === member.id;

  const ready = data.clips.filter((c) => c.status === "ready");
  const citable = isStaff
    ? ready
    : ready.filter((c) => data.owners[c.session_id] === member.id);
  const cited = new Set(
    data.facts.flatMap((f) => f.evidence.map((e) => e.clip_id)),
  );
  const uncited = data.session ? ready.filter((c) => !cited.has(c.id)) : [];

  const backTo = data.session
    ? `/app/sessions/${data.session.id}`
    : `/app/dogs/${data.dogId}`;
  const title = dog ? `Review - ${dog.name}` : "Review";

  const nextAfter = (f: Fact): string | null => {
    const list = shown;
    const i = list.findIndex((x) => x.id === f.id);
    return list[i + 1]?.id ?? list[i - 1]?.id ?? null;
  };

  const confirmedDone = (f: Fact) => {
    const left = Math.max(0, draftsNow - 1);
    setLive(`Fact confirmed. ${left} left to review.`);
    focusAfter.current = filter === "review" ? nextAfter(f) : null;
    reload();
  };

  const removeFact = async () => {
    if (!deleting) return;
    const f = deleting;
    setBusy(true);
    setFailure(null);
    try {
      await api.deleteFact(f.id);
      setDeleting(null);
      toast.success("Fact deleted.");
      const left =
        f.status === "draft" ? Math.max(0, draftsNow - 1) : draftsNow;
      setLive(`Fact deleted. ${left} left to review.`);
      focusAfter.current = nextAfter(f);
      reload();
    } catch (e) {
      setDeleting(null);
      if (isApiError(e) && e.code === "not_found") {
        toast.error("This fact was already deleted.");
        reload();
      } else {
        setFailure(e);
      }
    } finally {
      setBusy(false);
    }
  };

  const filters: { id: Filter; label: string }[] = [
    { id: "review", label: `To review (${drafts.length})` },
    { id: "confirmed", label: "Confirmed" },
    { id: "all", label: "All" },
  ];

  return (
    <Screen
      title={title}
      backTo={backTo}
      action={
        <BlockedButton blocked={!consented} onClick={() => setAdding({})}>
          Add a fact by hand
        </BlockedButton>
      }
    >
      <h1>Review</h1>
      <p>{`${drafts.length} to review - ${confirmed.length} confirmed`}</p>
      <p role="status" className="wm-visually-hidden">
        {live}
      </p>
      {wordingMode === "rules_only" ? (
        <p className="wm-muted">Wording check: banned-word list only.</p>
      ) : null}

      <div className="wm-row" role="group" aria-label="Show facts">
        {filters.map((f) => (
          <button
            key={f.id}
            type="button"
            className="wm-btn wm-btn--secondary wm-filter"
            aria-pressed={filter === f.id}
            onClick={() => setFilter(f.id)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {failure ? (
        <ErrorNotice
          error={failure}
          table={{
            not_own_session:
              "You can delete only facts from your own sessions.",
          }}
        />
      ) : null}

      {data.facts.length > 0 && drafts.length === 0 ? (
        <div className="wm-notice wm-notice--ok">
          <p className="wm-strong">All facts here are confirmed.</p>
          {isStaff && checklist?.ready_to_publish && dog ? (
            <Link to={`/app/dogs/${dog.id}`} className="wm-btn">
              {`Publish ${dog.name}`}
            </Link>
          ) : (
            <Link
              to={`/app/dogs/${data.dogId}`}
              className="wm-btn wm-btn--secondary"
            >
              Go to dog
            </Link>
          )}
        </div>
      ) : null}

      {data.facts.length === 0 ? (
        <div className="wm-stack">
          <p>No facts were drafted for this session.</p>
          <p>Add a fact by hand, or check that your clips have narration.</p>
        </div>
      ) : shown.length === 0 ? (
        <p>
          {filter === "confirmed"
            ? "No confirmed facts yet."
            : "Nothing left to review."}
        </p>
      ) : (
        <div className="wm-stack">
          {shown.map((f) => (
            <FactCard
              key={f.id}
              fact={f}
              wordingMode={wordingMode}
              canEdit={canEdit(f)}
              dogPublished={dogPublished}
              onReload={reload}
              onEdit={setEditing}
              onDelete={setDeleting}
              onConfirmed={confirmedDone}
            />
          ))}
        </div>
      )}

      {uncited.length > 0 ? (
        <ul className="wm-list">
          {uncited.map((c) => (
            <li key={c.id}>
              <p>{`Clip ${c.ordinal}: No facts were drafted from this clip. Add one by hand if you saw something.`}</p>
              <button
                type="button"
                className="wm-btn wm-btn--secondary"
                disabled={!consented}
                onClick={() => setAdding({ clipId: c.id })}
              >
                Add a fact by hand
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {editing ? (
        <EditFactSheet
          fact={editing}
          clips={citable}
          onClose={() => setEditing(null)}
          onSaved={reload}
          onReload={reload}
        />
      ) : null}

      {adding ? (
        <AddFactSheet
          dogId={data.dogId}
          clips={citable}
          initialClipId={adding.clipId}
          onClose={() => setAdding(null)}
          onAdded={reload}
        />
      ) : null}

      {deleting ? (
        <ConfirmDialog
          title="Delete this fact?"
          confirmLabel="Delete fact"
          danger
          busy={busy}
          onConfirm={() => void removeFact()}
          onCancel={() => setDeleting(null)}
        >
          {deleting.status === "confirmed" ? (
            <p>This fact is confirmed. It leaves the public profile now.</p>
          ) : null}
          <p>
            It disappears from every page right away. This cannot be undone.
          </p>
        </ConfirmDialog>
      ) : null}
    </Screen>
  );
}
