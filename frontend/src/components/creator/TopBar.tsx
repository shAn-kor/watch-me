import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../../state/AuthProvider";
import { Dialog } from "./Dialog";
import { useToast } from "./Toast";

interface Props {
  title: string;
  /** Link target for Back. Omit on S3. */
  backTo?: string;
  /** Used instead of `backTo` when Back needs a check first (unsaved changes). */
  onBack?: () => void;
}

/** Back, screen name and the Menu sheet (05 section 2.1). */
export function TopBar({ title, backTo, onBack }: Props) {
  const [open, setOpen] = useState(false);
  return (
    <header className="wm-topbar">
      <span className="wm-brand">Watch Me!</span>
      {onBack ? (
        <button
          type="button"
          className="wm-btn wm-btn--secondary wm-topbar__back"
          onClick={onBack}
        >
          <span aria-hidden="true">&lt;</span> Back
        </button>
      ) : backTo ? (
        <Link to={backTo} className="wm-btn wm-btn--secondary wm-topbar__back">
          <span aria-hidden="true">&lt;</span> Back
        </Link>
      ) : null}
      <span className="wm-topbar__title">{title}</span>
      <button
        type="button"
        className="wm-btn wm-btn--secondary"
        onClick={() => setOpen(true)}
      >
        Menu
      </button>
      {open ? <MenuSheet onClose={() => setOpen(false)} /> : null}
    </header>
  );
}

function MenuSheet({ onClose }: { onClose: () => void }) {
  const auth = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  const signOut = async () => {
    setBusy(true);
    const confirmed = await auth.logout(() => navigate("/app/login"));
    if (!confirmed)
      toast.error(
        "You were signed out on this device. The server could not confirm it.",
      );
  };

  return (
    <Dialog title="Menu" variant="sheet" onClose={onClose} busy={busy}>
      <nav aria-label="Menu" className="wm-stack">
        <Link to="/app/dogs" className="wm-menu-link" onClick={onClose}>
          Dogs
        </Link>
        <Link to="/app/consent" className="wm-menu-link" onClick={onClose}>
          Consent notice
        </Link>
        <Link to="/terms" className="wm-menu-link" onClick={onClose}>
          Terms
        </Link>
        <button
          type="button"
          className="wm-btn wm-btn--secondary"
          onClick={signOut}
          disabled={busy}
        >
          Sign out
        </button>
      </nav>
      {auth.member ? (
        <p className="wm-muted">
          {auth.member.display_name}, {auth.member.role}
        </p>
      ) : null}
    </Dialog>
  );
}
