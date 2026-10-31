import type { ReactNode } from "react";
import "../creator/creator.css";
import "./public.css";
import { PublicTopBar } from "./PublicTopBar";

/**
 * Page frame of the public screens (S9, S10): the same column, type and tokens
 * as the creator screens, with the plain public top bar.
 */
export function PublicPage({
  orgName,
  children,
}: {
  orgName?: string;
  children: ReactNode;
}) {
  return (
    <div className="wm-page wm-public">
      <PublicTopBar orgName={orgName} />
      <div className="wm-content">{children}</div>
    </div>
  );
}
