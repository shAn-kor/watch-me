import { useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { isApiError } from "../api/errors";
import { useApi } from "../api/provider";
import type { Limits, Member, Org } from "../api/types";
import { LIMITS_FALLBACK } from "../lib/constants";

export type AuthStatus = "idle" | "loading" | "authed" | "anon" | "error";

export interface AuthValue {
  status: AuthStatus;
  member: Member | null;
  org: Org | null;
  limits: Limits;
  /** Set when a signed-in session ended on its own (401), for the login notice. */
  wasAuthed: boolean;
  /** True right after a successful login, so login can route to the consent page once. */
  freshLogin: boolean;
  error: unknown;
  /** Reads `GET /api/me` once (creator routes only; public pages never call it). */
  load: () => void;
  retry: () => void;
  login: (email: string, password: string) => Promise<Member>;
  /** Resolves true when the server confirmed. `leave` runs before the state clears. */
  logout: (leave?: () => void) => Promise<boolean>;
  acceptConsent: (version: string) => Promise<Member>;
  /** A 401 on any call: back to signed-out state. */
  expire: () => void;
  clearFresh: () => void;
}

const FALLBACK: Limits = {
  ...LIMITS_FALLBACK,
  allowed_extensions: [...LIMITS_FALLBACK.allowed_extensions],
  wording_check: "model",
};

interface State {
  status: AuthStatus;
  member: Member | null;
  org: Org | null;
  limits: Limits;
  wasAuthed: boolean;
  freshLogin: boolean;
  error: unknown;
}

const INITIAL: State = {
  status: "idle",
  member: null,
  org: null,
  limits: FALLBACK,
  wasAuthed: false,
  freshLogin: false,
  error: null,
};

const AuthContext = createContext<AuthValue | null>(null);

function isUnauthenticated(e: unknown): boolean {
  return isApiError(e) && e.code === "unauthenticated";
}

/**
 * Signed-in member, org and `limits` in memory (06 section 6.4). The CSRF token
 * lives in the ApiClient. Nothing is read until a creator route asks (`load`).
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const api = useApi();
  const qc = useQueryClient();
  const [state, setState] = useState<State>(INITIAL);
  const started = useRef(false);

  const fetchMe = useCallback(async () => {
    setState((s) => ({ ...s, status: "loading", error: null }));
    try {
      const me = await api.getMe();
      setState((s) => ({
        ...s,
        status: "authed",
        member: me.member,
        org: me.org,
        limits: me.limits,
        error: null,
      }));
    } catch (e) {
      if (isUnauthenticated(e)) {
        setState((s) => ({ ...s, status: "anon", member: null, org: null }));
      } else {
        setState((s) => ({ ...s, status: "error", error: e }));
      }
    }
  }, [api]);

  const load = useCallback(() => {
    if (started.current) return;
    started.current = true;
    void fetchMe();
  }, [fetchMe]);

  const retry = useCallback(() => {
    void fetchMe();
  }, [fetchMe]);

  const expire = useCallback(() => {
    started.current = true;
    setState((s) =>
      s.status === "anon" ? s : { ...s, status: "anon", member: null, org: null, wasAuthed: s.status === "authed" || s.wasAuthed },
    );
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      await api.login(email, password);
      const me = await api.getMe();
      qc.clear();
      started.current = true;
      setState({
        status: "authed",
        member: me.member,
        org: me.org,
        limits: me.limits,
        wasAuthed: false,
        freshLogin: true,
        error: null,
      });
      return me.member;
    },
    [api, qc],
  );

  const logout = useCallback(
    async (leave?: () => void) => {
      let confirmed = true;
      try {
        await api.logout();
      } catch {
        confirmed = false;
      }
      leave?.();
      qc.clear();
      started.current = true;
      setState({ ...INITIAL, status: "anon" });
      return confirmed;
    },
    [api, qc],
  );

  const acceptConsent = useCallback(
    async (version: string) => {
      const r = await api.acceptConsent(version);
      setState((s) => ({ ...s, member: r.member }));
      return r.member;
    },
    [api],
  );

  const clearFresh = useCallback(() => {
    setState((s) => (s.freshLogin ? { ...s, freshLogin: false } : s));
  }, []);

  // Any 401 in a query or mutation ends the session (05 section 2.3).
  useEffect(() => {
    const unsubQ = qc.getQueryCache().subscribe((ev) => {
      if (ev.type === "updated" && ev.action.type === "error" && isUnauthenticated(ev.action.error)) {
        expire();
      }
    });
    const unsubM = qc.getMutationCache().subscribe((ev) => {
      if (ev.type === "updated" && ev.action.type === "error" && isUnauthenticated(ev.action.error)) {
        expire();
      }
    });
    return () => {
      unsubQ();
      unsubM();
    };
  }, [qc, expire]);

  const value = useMemo<AuthValue>(
    () => ({ ...state, load, retry, login, logout, acceptConsent, expire, clearFresh }),
    [state, load, retry, login, logout, acceptConsent, expire, clearFresh],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const v = useContext(AuthContext);
  if (!v) throw new Error("useAuth needs an <AuthProvider>");
  return v;
}

/** `useAuth` plus a first `GET /api/me` (screens can run without a route guard). */
export function useEnsureAuth(): AuthValue {
  const auth = useAuth();
  const { load } = auth;
  useEffect(() => {
    load();
  }, [load]);
  return auth;
}

/** The signed-in member inside a guarded route. */
export function useMember(): Member {
  const { member } = useAuth();
  if (!member) throw new Error("useMember used outside RequireMember");
  return member;
}
