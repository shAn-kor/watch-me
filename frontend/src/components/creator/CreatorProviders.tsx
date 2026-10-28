import type { ReactNode } from "react";
import { AuthProvider } from "../../state/AuthProvider";
import "./creator.css";
import { ToastProvider } from "./Toast";

/** Everything the creator screens share: auth state and toasts (06 section 6). */
export function CreatorProviders({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <ToastProvider>{children}</ToastProvider>
    </AuthProvider>
  );
}
