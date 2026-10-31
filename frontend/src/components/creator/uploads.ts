import { useCallback, useEffect, useRef, useState } from "react";
import { isApiError } from "../../api/errors";
import type { ApiClient } from "../../api/client";
import type { Limits } from "../../api/types";
import { globalText } from "./errors";
import { waitText } from "./format";
import type { SessionFeed } from "./sessionFeed";

export interface LocalUpload {
  key: string;
  file: File;
  requestId: string;
  state: "waiting" | "uploading" | "failed";
  percent: number;
  error: string | null;
  retryable: boolean;
  consentLink: boolean;
}

function newId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function")
    return crypto.randomUUID();
  return `${Date.now().toString(16)}-${Math.random().toString(16).slice(2)}`;
}

function megabytes(bytes: number): string {
  return `${Math.round(bytes / (1024 * 1024))} MB`;
}

const TYPE_TEXT = "This file type is not supported. Use an MP4 or MOV video.";
const STOPPED_TEXT =
  "The upload stopped before it finished. Check your connection and try again.";

/** Automatic retries after `service_busy` (503 + Retry-After), then a manual retry. */
export const BUSY_RETRIES = 2;
const BUSY_WAIT_MAX_S = 5;

function busyDelayMs(e: { retryAfter: number | null }): number {
  const s = e.retryAfter ?? 1;
  return Math.min(Math.max(s, 0), BUSY_WAIT_MAX_S) * 1000;
}

/** Resolves after `ms`, or early when `signal` aborts. */
function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) return resolve();
    const done = () => {
      clearTimeout(t);
      signal.removeEventListener("abort", done);
      resolve();
    };
    const t = setTimeout(done, ms);
    signal.addEventListener("abort", done);
  });
}

function sizeText(limits: Limits, bytes?: number): string {
  return `This file is larger than ${megabytes(bytes ?? limits.max_clip_bytes)}. Choose a smaller file or film a shorter clip.`;
}

export interface UploadFailure {
  text: string;
  retryable: boolean;
  consentLink: boolean;
}

/** The upload error table of 05 S7. */
export function uploadFailure(e: unknown, limits: Limits): UploadFailure {
  const plain = (text: string, retryable = false): UploadFailure => ({
    text,
    retryable,
    consentLink: false,
  });
  if (!isApiError(e)) return plain(STOPPED_TEXT, true);
  switch (e.code) {
    case "consent_required":
      return {
        text: "Accept the consent notice before you upload.",
        retryable: false,
        consentLink: true,
      };
    case "not_found":
      return plain("This session no longer exists.");
    case "not_own_session":
      return plain(
        "Only the member who started this session, or staff, can add clips.",
      );
    case "invalid_state":
      return plain(
        "This session no longer takes clips. It may be submitted already, or the dog is published or adopted.",
      );
    case "clip_limit_reached":
      return plain(
        `This session already has ${limits.max_clips_per_session} clips. Delete one to add another.`,
      );
    case "file_too_large":
      return plain(sizeText(limits, e.details.max_bytes));
    case "unsupported_file_type":
      return e.details.reason === "probe_timeout"
        ? plain(
            "We could not read this video in time. Try again, or choose a different file.",
            true,
          )
        : plain(TYPE_TEXT);
    case "upload_incomplete":
      return plain(STOPPED_TEXT, true);
    case "clip_too_long": {
      const max = e.details.max_s ?? limits.max_clip_s;
      const dur = Math.round(e.details.duration_s ?? 0);
      return plain(
        `This clip is ${dur} s long. The limit is ${Math.round(max / 60)} minutes (${max} s). Trim it or film a shorter clip.`,
      );
    }
    case "storage_unavailable":
      return plain(
        "The server cannot store files right now. Try again in a few minutes.",
        true,
      );
    case "service_busy":
      return plain("The server is busy right now. Try again in a moment.", true);
    case "rate_limited":
      return plain(
        `You have reached the limit of 20 uploads per hour. ${waitText(e.retryAfter)}`,
        true,
      );
    case "internal_error":
      return plain(globalText(e), true);
    default:
      return plain(globalText(e));
  }
}

/**
 * Client precheck for type (01 5.3: the server decides by ffprobe). Send the
 * file unless it clearly is not a video: an allowed extension, any `video/*`
 * type, a missing extension or an empty type all go through.
 */
export function looksLikeVideo(file: File, allowed: string[]): boolean {
  const name = file.name.toLowerCase();
  if (allowed.some((ext) => name.endsWith(ext.toLowerCase()))) return true;
  const type = file.type.toLowerCase();
  if (type === "" || type.startsWith("video/")) return true;
  const dot = name.lastIndexOf(".");
  if (dot <= 0 || dot === name.length - 1) return true;
  return false;
}

interface Options {
  api: ApiClient;
  sessionId: string;
  limits: Limits;
  /** Clips the server already lists. */
  existing: number;
  feed: SessionFeed;
  onExpire: () => void;
  onNoAudio: (clipId: string) => void;
}

/**
 * Sequential upload queue (05 S7): one file at a time in the chosen order, a
 * fresh `client_request_id` per file that a retry reuses. The queue lives in
 * a ref and is mirrored into state for rendering.
 */
export function useUploads({
  api,
  sessionId,
  limits,
  existing,
  feed,
  onExpire,
  onNoAudio,
}: Options) {
  const [items, setItems] = useState<LocalUpload[]>([]);
  const queue = useRef<LocalUpload[]>([]);
  const running = useRef(false);
  const alive = useRef(false);
  /** One controller per file that is uploading now. */
  const controllers = useRef(new Map<string, AbortController>());

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const sync = useCallback(() => {
    if (alive.current) setItems(queue.current.map((x) => ({ ...x })));
  }, []);

  const pump = useCallback(async () => {
    if (running.current) return;
    running.current = true;
    try {
      while (alive.current) {
        const next = queue.current.find((x) => x.state === "waiting");
        if (!next) break;
        next.state = "uploading";
        next.percent = 0;
        next.error = null;
        const ctl = new AbortController();
        controllers.current.set(next.key, ctl);
        sync();
        try {
          let res;
          for (let busy = 0; ; busy++) {
            try {
              res = await api.uploadClip(sessionId, next.file, {
                clientRequestId: next.requestId,
                signal: ctl.signal,
                onProgress: (loaded, total) => {
                  next.percent =
                    total > 0
                      ? Math.min(100, Math.round((loaded * 100) / total))
                      : 0;
                  sync();
                },
              });
              break;
            } catch (err) {
              // SQLite stayed locked: wait Retry-After (capped), then resend
              // with the same client_request_id so a landed upload is reused.
              if (
                !isApiError(err) ||
                err.code !== "service_busy" ||
                busy >= BUSY_RETRIES ||
                ctl.signal.aborted
              )
                throw err;
              next.percent = 0;
              sync();
              await sleep(busyDelayMs(err), ctl.signal);
              if (ctl.signal.aborted) throw err;
            }
          }
          // Cancelled just as the server answered: the row is already gone.
          if (ctl.signal.aborted) continue;
          queue.current = queue.current.filter((x) => x !== next);
          feed.addClip(res.clip);
          if (res.warnings.includes("no_audio_track")) onNoAudio(res.clip.id);
          sync();
        } catch (e) {
          // Cancel is not an error: no failed row, no toast (05 S7).
          if (ctl.signal.aborted) continue;
          if (isApiError(e) && e.code === "unauthenticated") onExpire();
          const f = uploadFailure(e, limits);
          next.state = "failed";
          next.error = f.text;
          next.retryable = f.retryable;
          next.consentLink = f.consentLink;
          sync();
        } finally {
          controllers.current.delete(next.key);
        }
      }
    } finally {
      running.current = false;
    }
  }, [api, sessionId, limits, feed, onExpire, onNoAudio, sync]);

  const add = useCallback(
    (files: File[]) => {
      for (const file of files) {
        const active = queue.current.filter((x) => x.state !== "failed").length;
        const entry: LocalUpload = {
          key: newId(),
          file,
          requestId: newId(),
          state: "waiting",
          percent: 0,
          error: null,
          retryable: false,
          consentLink: false,
        };
        const okType = looksLikeVideo(file, limits.allowed_extensions);
        let error: string | null = null;
        if (existing + active >= limits.max_clips_per_session) {
          error = `This session already has ${limits.max_clips_per_session} clips. Delete one to add another.`;
        } else if (!okType) {
          error = TYPE_TEXT;
        } else if (file.size > limits.max_clip_bytes) {
          error = sizeText(limits);
        }
        if (error) {
          entry.state = "failed";
          entry.error = error;
        }
        queue.current.push(entry);
      }
      sync();
      void pump();
    },
    [existing, limits, pump, sync],
  );

  const retry = useCallback(
    (key: string) => {
      const item = queue.current.find((x) => x.key === key);
      if (!item || item.state !== "failed") return;
      item.state = "waiting";
      item.error = null;
      sync();
      void pump();
    },
    [pump, sync],
  );

  const remove = useCallback(
    (key: string) => {
      queue.current = queue.current.filter((x) => x.key !== key);
      sync();
    },
    [sync],
  );

  /** Stop a running upload and drop its row. Nothing is shown as failed. */
  const cancel = useCallback(
    (key: string) => {
      const item = queue.current.find((x) => x.key === key);
      if (!item || item.state !== "uploading") return;
      controllers.current.get(key)?.abort();
      queue.current = queue.current.filter((x) => x !== item);
      sync();
    },
    [sync],
  );

  const pending = items.filter((x) => x.state !== "failed").length;
  const busy = items.some(
    (x) => x.state === "waiting" || x.state === "uploading",
  );
  return { items, add, retry, remove, cancel, pending, busy };
}
