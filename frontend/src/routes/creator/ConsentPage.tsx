import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { isApiError } from "../../api/errors";
import { CONSENT_VERSION } from "../../components/creator/constants";
import { ErrorNotice } from "../../components/creator/errors";
import { formatInstant, safeReturnTo } from "../../components/creator/format";
import { useToast } from "../../components/creator/Toast";
import { Loading, Screen } from "../../components/creator/ui";
import { useEnsureAuth } from "../../state/AuthProvider";

/** S2 Consent notice (05 section 5). */
export default function ConsentPage() {
  const auth = useEnsureAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const [params] = useSearchParams();
  const returnTo = safeReturnTo(params.get("returnTo"));
  const [ticked, setTicked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);

  if (!auth.member) {
    return (
      <Screen title="Consent notice" backTo="/app/dogs">
        <Loading text="Loading..." />
      </Screen>
    );
  }
  const acceptedAt = auth.member.consented_at;

  const accept = async () => {
    setBusy(true);
    setFailure(null);
    try {
      await auth.acceptConsent(CONSENT_VERSION);
      toast.success("Consent saved.");
      navigate(returnTo ?? "/app/dogs", { replace: true });
    } catch (e) {
      setBusy(false);
      setFailure(e);
    }
  };

  const mismatch =
    isApiError(failure) &&
    failure.code === "validation_error" &&
    (failure.details.fields ?? []).some(
      (f) => f.problem === "version_mismatch",
    );

  return (
    <Screen
      title="Consent notice"
      backTo="/app/dogs"
      action={
        acceptedAt ? (
          <Link to="/app/dogs" className="wm-btn">
            Back to dogs
          </Link>
        ) : (
          <button
            type="button"
            className="wm-btn"
            disabled={!ticked || busy}
            onClick={accept}
          >
            {busy ? "Saving..." : "Accept and continue"}
          </button>
        )
      }
    >
      <h1>Faces and voices in clips</h1>
      <p>Clips can show your face and record your voice. If you accept:</p>
      <ul>
        <li>
          Clips go to an AI service that writes a transcript and drafts facts.
        </li>
        <li>
          A clip is public only after staff publish the dog and a confirmed fact
          uses that clip. Visitors can then play the whole clip, not only the
          cited part.
        </li>
        <li>
          Staff can delete a clip or a dog. Copies already downloaded cannot be
          recalled.
        </li>
        <li>Clips are not used to train AI models in this version.</li>
      </ul>
      <p>Only the dog and members who accepted this notice may be in a clip.</p>
      {acceptedAt ? (
        <p className="wm-strong">
          You accepted this notice on {formatInstant(acceptedAt)}.
        </p>
      ) : null}
      <div className="wm-check">
        <input
          id="consent-box"
          type="checkbox"
          checked={Boolean(acceptedAt) || ticked}
          readOnly={Boolean(acceptedAt)}
          disabled={Boolean(acceptedAt)}
          onChange={(e) => setTicked(e.target.checked)}
        />
        <label htmlFor="consent-box">
          I agree that my face and voice may appear in clips I upload.
        </label>
      </div>
      {failure ? (
        mismatch ? (
          <div role="alert" className="wm-notice wm-notice--error">
            <p>
              This notice was updated. Reload the page to read the new version.
            </p>
            <button
              type="button"
              className="wm-btn"
              onClick={() => window.location.reload()}
            >
              Reload
            </button>
          </div>
        ) : (
          <ErrorNotice
            error={failure}
            table={{ validation_error: "Tick the box to continue." }}
          />
        )
      ) : null}
      {acceptedAt ? null : (
        <p>
          <Link to="/app/dogs">Not now</Link>
        </p>
      )}
    </Screen>
  );
}
