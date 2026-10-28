import { Navigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { ErrorNotice } from "../components/creator/errors";
import { safeReturnTo } from "../components/creator/format";
import { useEnsureAuth } from "../state/AuthProvider";

export interface GuardProps {
  children: ReactNode;
}

function Checking() {
  return (
    <p role="status" className="wm-page wm-content wm-muted">
      Checking your session...
    </p>
  );
}

/** Redirects to /app/login (keeping the route in `returnTo`) when nobody is signed in. */
export function RequireMember({ children }: GuardProps) {
  const auth = useEnsureAuth();
  const loc = useLocation();
  if (auth.status === "idle" || auth.status === "loading") return <Checking />;
  if (auth.status === "error") {
    return (
      <div className="wm-page wm-content">
        <ErrorNotice error={auth.error} onRetry={auth.retry} />
      </div>
    );
  }
  if (auth.status === "anon") {
    const back = encodeURIComponent(loc.pathname + loc.search);
    return <Navigate to={`/app/login?returnTo=${back}${auth.wasAuthed ? "&ended=1" : ""}`} replace />;
  }
  return <>{children}</>;
}

/** Redirects to /app/consent (keeping the original route) when consent is missing. */
export function RequireConsent({ children }: GuardProps) {
  const auth = useEnsureAuth();
  const loc = useLocation();
  if (auth.status !== "authed" || !auth.member) return null;
  if (!auth.member.consented_at) {
    const back = encodeURIComponent(loc.pathname + loc.search);
    return <Navigate to={`/app/consent?returnTo=${back}`} replace />;
  }
  return <>{children}</>;
}

/** Hides staff-only screens from volunteers. */
export function RequireStaff({ children }: GuardProps) {
  const auth = useEnsureAuth();
  if (auth.status !== "authed" || !auth.member) return null;
  if (auth.member.role !== "staff") {
    return (
      <div className="wm-page wm-content">
        <p>Only staff can open this page.</p>
      </div>
    );
  }
  return <>{children}</>;
}

/** Redirects a signed-in member away from /app/login. */
export function RedirectIfAuthed({ children }: GuardProps) {
  const auth = useEnsureAuth();
  const loc = useLocation();
  if (auth.status === "idle" || auth.status === "loading") return <Checking />;
  if (auth.status === "authed" && !auth.freshLogin) {
    const target = safeReturnTo(new URLSearchParams(loc.search).get("returnTo")) ?? "/app/dogs";
    return <Navigate to={target} replace />;
  }
  return <>{children}</>;
}
