import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { isApiError } from "../../api/errors";
import { ErrorNotice, Notice } from "../../components/creator/errors";
import { safeReturnTo, waitText } from "../../components/creator/format";
import { Field } from "../../components/creator/ui";
import { useAuth } from "../../state/AuthProvider";

/** S1 Login (05 section 5). */
export default function LoginPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const returnTo = safeReturnTo(params.get("returnTo"));
  const ended = params.get("ended") === "1";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [errors, setErrors] = useState<{ email?: string; password?: string }>(
    {},
  );
  const [failure, setFailure] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [lockedUntil, setLockedUntil] = useState<number | null>(null);
  const [lockText, setLockText] = useState<string | null>(null);

  // The rate-limit countdown re-enables the button when it ends.
  useEffect(() => {
    if (lockedUntil === null) return;
    const wait = Math.max(0, lockedUntil - Date.now());
    const t = setTimeout(() => {
      setLockedUntil(null);
      setLockText(null);
    }, wait);
    return () => clearTimeout(t);
  }, [lockedUntil]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy || lockedUntil !== null) return;
    const next: { email?: string; password?: string } = {};
    if (!email.trim()) next.email = "Enter your email.";
    if (!password) next.password = "Enter your password.";
    setErrors(next);
    setFailure(null);
    if (next.email || next.password) return;
    setBusy(true);
    try {
      const member = await auth.login(email.trim(), password);
      const target = member.consented_at
        ? (returnTo ?? "/app/dogs")
        : returnTo
          ? `/app/consent?returnTo=${encodeURIComponent(returnTo)}`
          : "/app/consent";
      navigate(target, { replace: true });
      auth.clearFresh();
    } catch (err) {
      setBusy(false);
      if (isApiError(err) && err.code === "rate_limited") {
        const seconds = err.retryAfter ?? 60;
        const minutes = Math.max(1, Math.ceil(seconds / 60));
        setLockText(`Too many sign-in attempts. ${waitText(minutes * 60)}`);
        setLockedUntil(Date.now() + seconds * 1000);
        return;
      }
      if (isApiError(err) && err.code === "validation_error") {
        const fields = err.details.fields ?? [];
        setErrors({
          email: fields.some((f) => f.path.endsWith("email"))
            ? "Enter a valid email address."
            : undefined,
          password: fields.some((f) => f.path.endsWith("password"))
            ? "Enter your password."
            : undefined,
        });
        return;
      }
      setFailure(err);
    }
  };

  return (
    <div className="wm-page wm-login">
      <div className="wm-login__intro">
        <p className="wm-brand">Watch Me!</p>
        <p className="wm-login__headline">Get to know the dog.<br />Watch the evidence.</p>
        <p>Turn everyday shelter clips into behavior profiles. Every confirmed fact links to the moment it happened.</p>
      </div>
      <div className="wm-login__panel">
        <h1>Sign in</h1>
        <p>Use the account your shelter gave you.</p>
        {ended ? (
          <Notice tone="info">
            <p>Your session ended. Sign in again.</p>
          </Notice>
        ) : null}
        {lockText ? (
          <div role="alert" className="wm-notice wm-notice--error">
            <p>{lockText}</p>
          </div>
        ) : null}
        {failure ? (
          <ErrorNotice
            error={failure}
            table={{ invalid_credentials: "Email or password is not correct." }}
          />
        ) : null}
        <form onSubmit={submit} noValidate>
          <Field label="Email" error={errors.email}>
            {({ id, describedBy, invalid }) => (
              <input
                id={id}
                type="email"
                autoComplete="username"
                value={email}
                readOnly={busy}
                aria-invalid={invalid}
                aria-describedby={describedBy}
                onChange={(e) => setEmail(e.target.value)}
              />
            )}
          </Field>
          <Field label="Password" error={errors.password}>
            {({ id, describedBy, invalid }) => (
              <div className="wm-row">
                <input
                  id={id}
                  type={show ? "text" : "password"}
                  autoComplete="current-password"
                  value={password}
                  readOnly={busy}
                  aria-invalid={invalid}
                  aria-describedby={describedBy}
                  style={{ flex: 1 }}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <button
                  type="button"
                  className="wm-btn wm-btn--secondary"
                  aria-pressed={show}
                  aria-label="Show password"
                  onClick={() => setShow(!show)}
                >
                  {show ? "Hide" : "Show"}
                </button>
              </div>
            )}
          </Field>
          <button
            type="submit"
            className="wm-btn"
            style={{ width: "100%" }}
            disabled={busy || lockedUntil !== null}
            aria-busy={busy}
          >
            {busy ? "Signing in..." : "Sign in"}
          </button>
        </form>
        <p className="wm-muted">
          Accounts are created by your shelter. Ask staff if you cannot sign in.
        </p>
      </div>
    </div>
  );
}
