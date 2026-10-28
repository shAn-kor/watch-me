import { useEffect } from "react";
import { BANNER_ID } from "../../lib/constants";

/** PUB-0 text. A constant: never read from the API. */
export const BANNER_TEXT =
  "These clips are short samples. They are not a behavior or safety assessment. Meet the dog and talk to the shelter before adopting.";

/** `bannerId` is only compared; a mismatch or a missing id is logged for developers. */
export function Banner({ bannerId }: { bannerId?: string }) {
  useEffect(() => {
    if (bannerId === undefined) return;
    if (bannerId !== BANNER_ID) {
      console.warn(
        `Public banner id is "${bannerId}", this build renders "${BANNER_ID}".`,
      );
    }
  }, [bannerId]);
  return (
    <aside
      aria-label="Important notice"
      className="public-banner"
      style={{ background: "#FFF4D6", padding: "12px", margin: "12px 0" }}
    >
      <p>{BANNER_TEXT}</p>
    </aside>
  );
}
