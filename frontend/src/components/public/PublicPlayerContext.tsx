import {
  createContext,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export interface ActiveClip {
  /** Card key: scope plus fact id, so a fact listed twice opens one at a time. */
  key: string;
  range: number;
}

interface Ctx {
  active: ActiveClip | null;
  open: (clip: ActiveClip) => void;
  close: () => void;
}

const PlayerCtx = createContext<Ctx | null>(null);

/** One shared player for the whole public page (05 S9): one card is open at a time. */
export function PublicPlayerProvider({ children }: { children: ReactNode }) {
  const [active, setActive] = useState<ActiveClip | null>(null);
  const value = useMemo<Ctx>(
    () => ({ active, open: setActive, close: () => setActive(null) }),
    [active],
  );
  return <PlayerCtx.Provider value={value}>{children}</PlayerCtx.Provider>;
}

export function usePublicPlayer(): Ctx {
  const c = useContext(PlayerCtx);
  if (!c) throw new Error("usePublicPlayer needs a <PublicPlayerProvider>");
  return c;
}
