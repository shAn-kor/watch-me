import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { isApiError } from "../../api/errors";
import { useApi } from "../../api/provider";
import type { Situation } from "../../api/types";
import {
  CAPTURE_RULES,
  SITUATION_HINTS,
} from "../../components/creator/constants";
import { ErrorNotice } from "../../components/creator/errors";
import { todayLocal } from "../../components/creator/format";
import { BlockedButton, Loading, Screen } from "../../components/creator/ui";
import { SITUATIONS } from "../../lib/constants";
import { useEnsureAuth } from "../../state/AuthProvider";

/** S6 New session: capture rules and situations (05 section 5). */
export default function SessionNewPage() {
  const { dogId = "" } = useParams();
  const api = useApi();
  const auth = useEnsureAuth();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const id = useId();
  const today = todayLocal();

  const [ack, setAck] = useState(false);
  const [picked, setPicked] = useState<Situation[]>([]);
  const [date, setDate] = useState(today);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);

  const q = useQuery({
    queryKey: ["dog", dogId],
    queryFn: () => api.getDog(dogId),
    enabled: auth.status === "authed",
  });

  if (q.isError && !q.data) {
    return (
      <Screen title="New session" backTo={`/app/dogs/${dogId}`}>
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
      <Screen title="New session" backTo={`/app/dogs/${dogId}`}>
        <Loading text="Loading dog..." onRetry={() => void q.refetch()} />
      </Screen>
    );
  }

  const { dog, coverage } = q.data;
  const title = `New session - ${dog.name}`;
  const isStaff = auth.member.role === "staff";
  const consented = Boolean(auth.member.consented_at);
  const back = `/app/dogs/${dogId}`;

  if (dog.status === "published") {
    return (
      <Screen title={title} backTo={back}>
        <h1>New session</h1>
        <p>This dog is published. Unpublish it before you add clips.</p>
        {isStaff ? (
          <Link to={back} className="wm-btn">
            Go to dog
          </Link>
        ) : (
          <p>Ask staff to unpublish this dog.</p>
        )}
      </Screen>
    );
  }
  if (dog.status === "adopted") {
    return (
      <Screen title={title} backTo={back}>
        <h1>New session</h1>
        <p>This dog is marked as adopted. Staff can reopen it to add clips.</p>
        <Link to={back} className="wm-btn">
          Go to dog
        </Link>
      </Screen>
    );
  }
  if (!consented) {
    return (
      <Screen title={title} backTo={back}>
        <h1>New session</h1>
        <p>Accept the consent notice before you add clips.</p>
        <Link to="/app/consent" className="wm-btn">
          Open consent notice
        </Link>
      </Screen>
    );
  }

  const blocked = !ack || picked.length === 0 || busy;

  const toggle = (code: Situation, on: boolean) => {
    const next = on ? [...picked, code] : picked.filter((c) => c !== code);
    // Keep the PRD order.
    setPicked(SITUATIONS.map((s) => s.code).filter((c) => next.includes(c)));
  };

  const start = async () => {
    setBusy(true);
    setFailure(null);
    try {
      const r = await api.createSession(dogId, {
        situations: picked,
        observed_on: date,
        capture_rules_ack: true,
      });
      navigate(`/app/sessions/${r.session.id}`);
    } catch (e) {
      setBusy(false);
      setFailure(e);
      if (isApiError(e) && e.code === "invalid_state") {
        void qc.invalidateQueries({ queryKey: ["dog", dogId] });
      }
    }
  };

  const fields =
    isApiError(failure) && failure.code === "validation_error"
      ? (failure.details.fields ?? [])
      : [];
  const validation = fields
    .map((f) =>
      f.path.includes("situations")
        ? "Pick at least one situation."
        : f.path.includes("capture_rules_ack")
          ? "Confirm that you read the capture rules."
          : f.path.includes("observed_on")
            ? "Choose today or an earlier date."
            : null,
    )
    .filter(Boolean)
    .join(" ");

  return (
    <Screen
      title={title}
      backTo={back}
      action={
        <BlockedButton blocked={blocked} onClick={() => void start()}>
          {busy ? "Starting..." : "Start session"}
        </BlockedButton>
      }
    >
      <h1>New session</h1>
      <h2>Capture rules</h2>
      <p>Read these before you film.</p>
      <ol aria-label="Capture rules">
        {CAPTURE_RULES.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ol>
      <div className="wm-check">
        <input
          id={`${id}-ack`}
          type="checkbox"
          checked={ack}
          onChange={(e) => setAck(e.target.checked)}
        />
        <label htmlFor={`${id}-ack`}>I have read the capture rules.</label>
      </div>

      <div className="wm-field">
        <fieldset>
          <legend>What will you film?</legend>
          <p className="wm-help">Pick at least one.</p>
          {SITUATIONS.map((s) => {
            const cov = coverage.by_situation.find(
              (c) => c.situation === s.code,
            );
            const covText =
              !cov || cov.clip_count === 0
                ? "Not observed yet"
                : `${cov.clip_count} ${cov.clip_count === 1 ? "clip" : "clips"}, ${Math.round(cov.filmed_s)} s so far`;
            return (
              <div key={s.code} className="wm-check">
                <input
                  id={`${id}-${s.code}`}
                  type="checkbox"
                  checked={picked.includes(s.code)}
                  aria-describedby={`${id}-${s.code}-d`}
                  onChange={(e) => toggle(s.code, e.target.checked)}
                />
                <div>
                  <label htmlFor={`${id}-${s.code}`} className="wm-strong">
                    {s.label}
                  </label>
                  <p id={`${id}-${s.code}-d`} className="wm-help">
                    {SITUATION_HINTS[s.code]} {covText}
                  </p>
                </div>
              </div>
            );
          })}
        </fieldset>
      </div>

      <div className="wm-field">
        <label htmlFor={`${id}-date`}>Date filmed</label>
        <input
          id={`${id}-date`}
          type="date"
          max={today}
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
      </div>

      {failure ? (
        <ErrorNotice
          error={failure}
          table={{
            consent_required: "Accept the consent notice before you add clips.",
            not_found: "This dog was not found. It may have been deleted.",
            invalid_state:
              "This dog cannot get new sessions right now. Open the dog page to see its status.",
            validation_error: validation || "Check the highlighted fields.",
          }}
          backLink={isApiError(failure) && failure.code === "not_found"}
        >
          {isApiError(failure) && failure.code === "invalid_state" ? (
            <p>
              <Link to={back}>Open the dog page</Link>
            </p>
          ) : null}
        </ErrorNotice>
      ) : null}
    </Screen>
  );
}
