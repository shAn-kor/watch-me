import { Link } from "react-router-dom";
import { Screen } from "../../components/creator/ui";

/** S0 Not found inside /app (05 section 5). */
export default function CreatorNotFoundPage() {
  return (
    <Screen title="Not found" backTo="/app/dogs">
      <h1>Page not found</h1>
      <p>This page does not exist.</p>
      <Link to="/app/dogs" className="wm-btn">
        Back to dogs
      </Link>
    </Screen>
  );
}
