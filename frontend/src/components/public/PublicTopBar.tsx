/** Plain header of the public screens: wordmark and, on a profile, the org name. */
export function PublicTopBar({ orgName }: { orgName?: string }) {
  return (
    <header className="wm-topbar public-topbar">
      <strong>Watch Me!</strong>
      {orgName && <span className="wm-topbar__title wm-muted">Shared by {orgName}</span>}
    </header>
  );
}
