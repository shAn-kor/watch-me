import { useQuery } from "@tanstack/react-query";
import { useCallback, useState, type ChangeEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { isApiError } from "../../api/errors";
import { useApi } from "../../api/provider";
import type { Clip } from "../../api/types";
import { ClipRow, LocalRow } from "../../components/creator/ClipRows";
import { ConfirmDialog, Dialog } from "../../components/creator/Dialog";
import { ErrorNotice, type ErrorTable } from "../../components/creator/errors";
import { formatDay, plural } from "../../components/creator/format";
import { useSessionFeed } from "../../components/creator/sessionFeed";
import { useToast } from "../../components/creator/Toast";
import { useUploads } from "../../components/creator/uploads";
import { BlockedButton, Loading, Screen } from "../../components/creator/ui";
import { RangePlayer } from "../../components/RangePlayer";
import { SITUATION_LABELS } from "../../lib/constants";
import { useEnsureAuth } from "../../state/AuthProvider";

const CONSENT_UPLOAD = "Accept the consent notice before you upload.";

const SESSION_ERRORS: ErrorTable = {
  not_found: "This session was not found. It may have been deleted.",
  consent_required: CONSENT_UPLOAD,
};

function deletedText(deleted: number, demoted: number): string {
  const parts: string[] = [];
  if (deleted > 0) parts.push(`${deleted} ${plural(deleted, "fact")} deleted`);
  if (demoted > 0)
    parts.push(`${demoted} ${plural(demoted, "fact")} set back to draft`);
  return parts.length > 0
    ? `Clip deleted. ${parts.join(", ")}.`
    : "Clip deleted.";
}

/** S7 Session: clips, upload and processing (05 section 5). */
export default function SessionPage() {
  const { sessionId = "" } = useParams();
  const api = useApi();
  const auth = useEnsureAuth();
  const toast = useToast();
  const authed = auth.status === "authed" && auth.member !== null;

  if (!authed) {
    return (
      <Screen title="Session" backTo="/app/dogs">
        <Loading text="Loading session..." />
      </Screen>
    );
  }
  return (
    <SessionBody
      key={sessionId}
      sessionId={sessionId}
      api={api}
      toast={toast}
    />
  );
}

function SessionBody({
  sessionId,
  api,
  toast,
}: {
  sessionId: string;
  api: ReturnType<typeof useApi>;
  toast: ReturnType<typeof useToast>;
}) {
  const auth = useEnsureAuth();
  const member = auth.member!;
  const { data, error, failing, feed } = useSessionFeed(sessionId);
  const dogId = data?.session.dog_id;
  const dogQuery = useQuery({
    queryKey: ["dog", dogId],
    queryFn: () => api.getDog(dogId as string),
    enabled: dogId !== undefined,
  });

  const [noSound, setNoSound] = useState<ReadonlySet<string>>(new Set());
  const [watching, setWatching] = useState<Clip | null>(null);
  const [deleting, setDeleting] = useState<Clip | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);
  const [failureTable, setFailureTable] = useState<ErrorTable>(SESSION_ERRORS);

  const onNoAudio = useCallback(
    (id: string) => setNoSound((s) => new Set(s).add(id)),
    [],
  );
  const uploads = useUploads({
    api,
    sessionId,
    limits: auth.limits,
    existing: data?.clips.length ?? 0,
    feed,
    onExpire: auth.expire,
    onNoAudio,
  });

  if (error && !data) {
    return (
      <Screen title="Session" backTo="/app/dogs">
        <ErrorNotice
          error={error}
          table={SESSION_ERRORS}
          backLink={isApiError(error) && error.code === "not_found"}
          onRetry={
            isApiError(error) && error.code === "not_found"
              ? undefined
              : () => void feed.refresh()
          }
        />
      </Screen>
    );
  }
  if (!data) {
    return (
      <Screen title="Session" backTo="/app/dogs">
        <Loading
          text="Loading session..."
          onRetry={() => void feed.refresh()}
        />
      </Screen>
    );
  }

  const { session, clips } = data;
  const dog = dogQuery.data?.dog ?? null;
  const consented = Boolean(member.consented_at);
  const isStaff = member.role === "staff";
  const canAct = isStaff || session.member_id === member.id;
  const isOpen = session.status === "open";
  const max = auth.limits.max_clips_per_session;
  const total = clips.length + uploads.pending;
  const dogBlocked =
    dog !== null && (dog.status === "published" || dog.status === "adopted");
  const addBlocked = !consented || dogBlocked || total >= max;
  const title = dog ? `Session - ${dog.name}` : "Session";

  const fail = (e: unknown, table: ErrorTable = {}) => {
    setFailureTable({ ...SESSION_ERRORS, ...table });
    setFailure(e);
  };

  const pick = (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (files.length > 0) uploads.add(files);
  };

  const activeClips = clips.filter(
    (c) =>
      c.status === "uploaded" ||
      c.status === "processing" ||
      c.status === "ready",
  );
  const failedClips = clips.filter((c) => c.status === "failed");
  const draftBlocked =
    activeClips.length === 0 ||
    uploads.busy ||
    !consented ||
    dogBlocked ||
    busy;

  const submit = async () => {
    setBusy(true);
    setFailure(null);
    try {
      const r = await api.submitSession(sessionId);
      feed.setSession(r.session);
    } catch (e) {
      fail(e, {
        not_own_session:
          "Only the member who started this session, or staff, can submit it.",
        invalid_state:
          "Add at least one clip first, or this session was already submitted. Reload the page.",
      });
    } finally {
      setBusy(false);
    }
  };

  const retryMerge = async () => {
    setBusy(true);
    setFailure(null);
    try {
      const r = await api.retryMerge(sessionId);
      feed.setSession(r.session);
    } catch (e) {
      fail(e, {
        not_own_session:
          "Only the member who started this session, or staff, can retry it.",
        invalid_state:
          "This session is not waiting for a retry. Reload the page.",
      });
    } finally {
      setBusy(false);
    }
  };

  const retryClip = async (clip: Clip) => {
    setBusy(true);
    setFailure(null);
    try {
      await api.retryClip(clip.id);
      await feed.refresh();
    } catch (e) {
      fail(e, {
        not_found: "This clip was not found.",
        not_own_session:
          "Only the member who started this session, or staff, can retry a clip.",
        invalid_state:
          "This clip cannot be retried. Delete it and upload a different file.",
      });
    } finally {
      setBusy(false);
    }
  };

  const deleteClip = async () => {
    if (!deleting) return;
    setBusy(true);
    setFailure(null);
    try {
      const r = await api.deleteClip(deleting.id);
      setDeleting(null);
      toast.success(deletedText(r.facts_deleted, r.facts_demoted));
      await feed.refresh();
    } catch (e) {
      setDeleting(null);
      if (isApiError(e) && e.code === "not_found") {
        toast.error("This clip was already deleted.");
        await feed.refresh();
      } else {
        fail(e, {
          not_own_session:
            "Only the member who started this session, or staff, can delete this clip.",
          forbidden_role:
            "A confirmed fact uses this clip. Ask staff to delete it.",
        });
      }
    } finally {
      setBusy(false);
    }
  };

  const draftCount = data.facts.filter((f) => f.status === "draft").length;
  const readyCount = clips.filter((c) => c.status === "ready").length;
  const hasRows = clips.length > 0 || uploads.items.length > 0;

  return (
    <Screen
      title={title}
      backTo={dog ? `/app/dogs/${dog.id}` : "/app/dogs"}
      action={
        isOpen && canAct ? (
          <div className="wm-stack">
            <BlockedButton blocked={draftBlocked} onClick={() => void submit()}>
              Draft facts
            </BlockedButton>
            {failedClips.length > 0 ? (
              <p className="wm-muted">
                {failedClips.length} failed {plural(failedClips.length, "clip")}{" "}
                will be skipped. Try them again first if you want them included.
              </p>
            ) : null}
          </div>
        ) : undefined
      }
    >
      <h1>Session</h1>
      <p className="wm-strong">{formatDay(session.observed_on)}</p>
      <p>{session.situations.map((s) => SITUATION_LABELS[s]).join(", ")}</p>
      <p className="wm-muted">Filmed by {session.owner_name}</p>

      {failing ? <p role="status">Connection problem. Trying again.</p> : null}
      {failure ? <ErrorNotice error={failure} table={failureTable} /> : null}

      {session.status === "processing" ? (
        <div className="wm-stack">
          <h2>Drafting facts</h2>
          <p>You can leave this page. Processing continues.</p>
        </div>
      ) : null}

      {session.status === "review" ? (
        <div className="wm-notice wm-notice--ok">
          <p className="wm-strong">Facts are ready to review.</p>
          <p>
            {draftCount} {plural(draftCount, "draft")} from {readyCount}{" "}
            {plural(readyCount, "clip")}.
          </p>
          <Link to={`/app/sessions/${session.id}/review`} className="wm-btn">
            Review facts
          </Link>
        </div>
      ) : null}

      {session.status === "failed" ? (
        <div className="wm-stack">
          {session.fail_code === "merge_failed" ? (
            <>
              <p className="wm-error-text">
                We could not finish drafting facts.
              </p>
              {canAct && consented ? (
                <button
                  type="button"
                  className="wm-btn"
                  disabled={busy}
                  onClick={() => void retryMerge()}
                >
                  Retry merge
                </button>
              ) : null}
            </>
          ) : (
            <p className="wm-error-text">
              No clip could be processed. Try a failed clip again, or start a
              new session and upload new clips.
            </p>
          )}
        </div>
      ) : null}

      {!canAct ? <p>This session belongs to another member.</p> : null}
      {canAct && !consented ? (
        <div className="wm-notice">
          <p>{CONSENT_UPLOAD}</p>
          <p>
            <Link to="/app/consent">Open consent notice</Link>
          </p>
        </div>
      ) : null}
      {canAct && consented && isOpen && dogBlocked && dog ? (
        <div className="wm-notice">
          <p>{`This dog is ${dog.status}. Staff must unpublish or reopen it before you add clips.`}</p>
        </div>
      ) : null}

      {isOpen && canAct ? (
        <section aria-labelledby="add-h">
          <h2 id="add-h">{`Add clips (${Math.min(total, max)} of ${max})`}</h2>
          <p className="wm-muted">MP4 or MOV, up to 2 minutes and 200 MB.</p>
          {total >= max ? (
            <p className="wm-muted">A session takes up to {max} clips.</p>
          ) : null}
          <div className="wm-row">
            <label className="wm-btn wm-file-btn" data-disabled={addBlocked || undefined}>
              Record with camera
              <input
                type="file"
                accept="video/*"
                capture="environment"
                disabled={addBlocked}
                className="wm-visually-hidden"
                onChange={pick}
              />
            </label>
            <label
              className="wm-btn wm-btn--secondary wm-file-btn"
              data-disabled={addBlocked || undefined}
            >
              Choose from library
              <input
                type="file"
                accept=".mp4,.mov,video/mp4,video/quicktime"
                multiple
                disabled={addBlocked}
                className="wm-visually-hidden"
                onChange={pick}
              />
            </label>
          </div>
          {!hasRows ? <p>Add your first clip.</p> : null}
        </section>
      ) : null}

      {hasRows ? (
        <ul className="wm-list" aria-live="polite">
          {clips.map((c) => (
            <ClipRow
              key={c.id}
              clip={c}
              canAct={canAct}
              canDeleteReady={isOpen}
              noSound={noSound.has(c.id)}
              busy={busy}
              onWatch={setWatching}
              onRetry={(clip) => void retryClip(clip)}
              onDelete={setDeleting}
            />
          ))}
          {uploads.items.map((item, i) => (
            <LocalRow
              key={item.key}
              item={item}
              ordinal={clips.length + i + 1}
              onRetry={uploads.retry}
              onRemove={uploads.remove}
              onCancel={uploads.cancel}
            />
          ))}
        </ul>
      ) : null}

      {watching && watching.media_url ? (
        <Dialog
          title={`Clip ${watching.ordinal}`}
          variant="sheet"
          onClose={() => setWatching(null)}
        >
          <RangePlayer
            src={watching.media_url}
            captionsSrc={watching.captions_url}
            startS={0}
            endS={watching.duration_s}
          />
        </Dialog>
      ) : null}

      {deleting ? (
        <ConfirmDialog
          title="Delete this clip?"
          confirmLabel="Delete clip"
          danger
          busy={busy}
          onConfirm={() => void deleteClip()}
          onCancel={() => setDeleting(null)}
        >
          <p>
            The clip is removed from storage. Facts that use only this clip are
            deleted. Facts with other clips go back to draft. This cannot be
            undone.
          </p>
        </ConfirmDialog>
      ) : null}
    </Screen>
  );
}
