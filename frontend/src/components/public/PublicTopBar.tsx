/** Plain header of the public screens: wordmark and, on a profile, the org name. */
export function PublicTopBar({ orgName }: { orgName?: string }) {
  return (
    <header className="public-topbar">
      <strong>Watch Me!</strong>
      {orgName && <span> Shared by {orgName}</span>}
    </header>
  );
}
