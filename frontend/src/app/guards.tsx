import type { ReactNode } from "react";

export interface GuardProps {
  children: ReactNode;
}

// Typed stubs (Phase 0). The real checks (FE-GRD-01) arrive with the
// AuthProvider in lane FE-C. Until then every guard passes its children.

/** Redirects to /app/login when there is no signed-in member. */
export function RequireMember({ children }: GuardProps) {
  return <>{children}</>;
}

/** Redirects to /app/consent (keeping the original route) when consent is missing. */
export function RequireConsent({ children }: GuardProps) {
  return <>{children}</>;
}

/** Hides staff-only screens from volunteers. */
export function RequireStaff({ children }: GuardProps) {
  return <>{children}</>;
}

/** Redirects a signed-in member away from /app/login. */
export function RedirectIfAuthed({ children }: GuardProps) {
  return <>{children}</>;
}
