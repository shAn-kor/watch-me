import { useEffect, useMemo, useSyncExternalStore } from "react";
import type { ApiClient } from "../../api/client";
import { isApiError } from "../../api/errors";
import { useApi } from "../../api/provider";
import type { Clip, Fact, Session, SessionSummaryResponse } from "../../api/types";
import { POLL_INTERVAL_MS } from "../../lib/constants";
import { useAuth } from "../../state/AuthProvider";

/** A polled session; `facts` is null until they were read once (review state). */
export type FeedSession = SessionSummaryResponse & { facts: Fact[] | null };

export interface FeedSnapshot {
  data: FeedSession | null;
  /** Set when the first load failed or the session is gone. */
  error: unknown;
  loading: boolean;
  /** Three polls in a row failed (05 section 2.2). */
  failing: boolean;
}

const SLOW_POLL_MS = 10_000;
const FAILS_BEFORE_NOTICE = 3;

/** Poll while the server still works on the session or on one of its clips. */
export function wantsPolling(d: SessionSummaryResponse): boolean {
  if (d.session.status === "processing") return true;
  return (
    d.session.status === "open" &&
    d.clips.some((c) => c.status === "uploaded" || c.status === "processing")
  );
}

/**
 * One session, loaded and then polled with `If-None-Match` (05 section 2.2).
 * Plain class so timers and refs stay out of render; React reads it through
 * `useSyncExternalStore`.
 */
export class SessionFeed {
  private snap: FeedSnapshot = {
    data: null,
    error: null,
    loading: true,
    failing: false,
  };
  private etag: string | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private failures = 0;
  private closed = true;
  private inflight = false;
  private again = false;
  /** `facts` in the snapshot were read with `getSession` (not null). */
  private factsLoaded = false;
  private listeners = new Set<() => void>();

  constructor(
    private readonly api: ApiClient,
    readonly id: string,
    private readonly onUnauthenticated: () => void,
  ) {}

  subscribe = (fn: () => void): (() => void) => {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  };

  getSnapshot = (): FeedSnapshot => this.snap;

  private set(next: Partial<FeedSnapshot>) {
    this.snap = { ...this.snap, ...next };
    for (const l of this.listeners) l();
  }

  start() {
    this.closed = false;
    document.addEventListener("visibilitychange", this.onVisibility);
    void this.load(true);
  }

  stop() {
    this.closed = true;
    this.clearTimer();
    document.removeEventListener("visibilitychange", this.onVisibility);
  }

  private onVisibility = () => {
    if (this.closed) return;
    if (document.visibilityState === "hidden") {
      this.clearTimer();
    } else if (this.snap.data && wantsPolling(this.snap.data)) {
      this.clearTimer();
      void this.load(false);
    }
  };

  private clearTimer() {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
  }

  private schedule() {
    this.clearTimer();
    const d = this.snap.data;
    if (this.closed || !d || !wantsPolling(d)) return;
    if (document.visibilityState === "hidden") return;
    const delay =
      this.failures >= FAILS_BEFORE_NOTICE ? SLOW_POLL_MS : POLL_INTERVAL_MS;
    this.timer = setTimeout(() => {
      this.timer = null;
      void this.load(false);
    }, delay);
  }

  /** Full read without `If-None-Match`; used after the member changed something. */
  refresh(): Promise<void> {
    this.clearTimer();
    return this.load(true);
  }

  private async load(full: boolean): Promise<void> {
    if (this.inflight) {
      if (full) this.again = true;
      return;
    }
    this.inflight = true;
    try {
      const r = await this.api.pollSession(this.id, full ? null : this.etag);
      if (this.closed) return;
      this.failures = 0;
      if (r.etag) this.etag = r.etag;
      if (r.notModified) {
        if (this.snap.failing) this.set({ failing: false });
      } else {
        // Polls ask for `include=none`, so they carry no facts. Keep the facts we
        // already read for this review; otherwise read them once below.
        const keep = this.factsLoaded && r.data.session.status === "review";
        if (!keep) this.factsLoaded = false;
        this.set({
          data: { ...r.data, facts: keep && this.snap.data ? this.snap.data.facts : null },
          error: null,
          loading: false,
          failing: false,
        });
      }
      await this.loadFacts();
    } catch (e) {
      if (this.closed) return;
      if (isApiError(e) && e.code === "unauthenticated") {
        this.onUnauthenticated();
        return;
      }
      if (!this.snap.data || (isApiError(e) && e.code === "not_found")) {
        this.set({ data: null, error: e, loading: false, failing: false });
        return;
      }
      this.failures += 1;
      if (this.failures >= FAILS_BEFORE_NOTICE && !this.snap.failing)
        this.set({ failing: true });
    } finally {
      this.inflight = false;
    }
    if (this.closed) return;
    if (this.again) {
      this.again = false;
      void this.load(true);
      return;
    }
    this.schedule();
  }

  /**
   * Facts are only shown once the session is in `review` (the "N drafts" line),
   * so the poll skips them and we read them once, when review is reached.
   */
  private async loadFacts(): Promise<void> {
    const d = this.snap.data;
    if (!d || d.session.status !== "review" || this.factsLoaded) return;
    try {
      const full = await this.api.getSession(this.id);
      if (this.closed) return;
      const cur = this.snap.data;
      if (!cur || cur.session.status !== "review") return;
      this.factsLoaded = true;
      this.set({ data: { ...cur, facts: full.facts } });
    } catch {
      // The summary line shows zero drafts. The review screen reads its own
      // facts, so nothing else depends on this call; a reload tries again.
    }
  }

  /** Put a freshly uploaded clip into the list without waiting for the next poll. */
  addClip(clip: Clip) {
    const d = this.snap.data;
    if (!d) return;
    const clips = [...d.clips.filter((c) => c.id !== clip.id), clip].sort(
      (a, b) => a.ordinal - b.ordinal,
    );
    this.set({
      data: {
        ...d,
        clips,
        progress: { ...d.progress, clips_total: clips.length },
      },
    });
    this.schedule();
  }

  /** Use the session object a call returned (submit, retry merge). */
  setSession(session: Session) {
    const d = this.snap.data;
    if (!d) return;
    this.set({ data: { ...d, session } });
    this.schedule();
  }
}

export function useSessionFeed(
  sessionId: string,
): FeedSnapshot & { feed: SessionFeed } {
  const api = useApi();
  const { expire } = useAuth();
  const feed = useMemo(
    () => new SessionFeed(api, sessionId, expire),
    [api, sessionId, expire],
  );
  useEffect(() => {
    feed.start();
    return () => feed.stop();
  }, [feed]);
  const snap = useSyncExternalStore(feed.subscribe, feed.getSnapshot);
  return { ...snap, feed };
}
