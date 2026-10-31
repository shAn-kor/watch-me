import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { PublicPage } from "../../components/public/PublicPage";

/**
 * S10. One page for unknown, unpublished, adopted and deleted profiles, and for
 * `/` and unknown paths. It never says which, and shows no banner or dog data.
 */
export default function NotAvailablePage() {
  const h1 = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    const prev = document.title;
    document.title = "Profile not available";
    h1.current?.focus();
    return () => {
      document.title = prev;
    };
  }, []);
  return (
    <PublicPage>
      <h1 ref={h1} tabIndex={-1}>
        This profile is not available
      </h1>
      <p>
        The link may be wrong, or the shelter has taken this profile down. Ask
        the shelter that shared the link.
      </p>
      <p>
        Watch Me! has no search page. A profile opens only from a link that a
        shelter shares.
      </p>
      <p>
        <Link to="/terms">Terms</Link>
      </p>
    </PublicPage>
  );
}
