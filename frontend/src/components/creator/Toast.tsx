import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

interface ToastItem {
  id: number;
  kind: "status" | "alert";
  text: string;
}

interface ToastApi {
  success: (text: string) => void;
  error: (text: string) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

const SUCCESS_MS = 6000;

/**
 * Success toasts: `role="status"`, gone after 6 s. Error toasts: `role="alert"`,
 * stay until dismissed (05 section 2.5). Each region exists only while it has items.
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const next = useRef(1);
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((id: number) => {
    const t = timers.current.get(id);
    if (t !== undefined) clearTimeout(t);
    timers.current.delete(id);
    setItems((xs) => xs.filter((x) => x.id !== id));
  }, []);

  const push = useCallback(
    (kind: ToastItem["kind"], text: string) => {
      const id = next.current++;
      setItems((xs) => [...xs, { id, kind, text }]);
      if (kind === "status") {
        timers.current.set(
          id,
          setTimeout(() => dismiss(id), SUCCESS_MS),
        );
      }
    },
    [dismiss],
  );

  useEffect(() => {
    const map = timers.current;
    return () => {
      for (const t of map.values()) clearTimeout(t);
      map.clear();
    };
  }, []);

  const api = useMemo<ToastApi>(
    () => ({
      success: (text) => push("status", text),
      error: (text) => push("alert", text),
    }),
    [push],
  );

  const ok = items.filter((x) => x.kind === "status");
  const bad = items.filter((x) => x.kind === "alert");
  return (
    <ToastContext.Provider value={api}>
      {children}
      {ok.length > 0 ? (
        <div role="status" className="wm-toasts">
          {ok.map((x) => (
            <p key={x.id} className="wm-toast">
              {x.text}
            </p>
          ))}
        </div>
      ) : null}
      {bad.length > 0 ? (
        <div role="alert" className="wm-toasts">
          {bad.map((x) => (
            <p key={x.id} className="wm-toast wm-toast--error">
              {x.text}{" "}
              <button type="button" className="wm-link-btn" onClick={() => dismiss(x.id)}>
                Dismiss
              </button>
            </p>
          ))}
        </div>
      ) : null}
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const v = useContext(ToastContext);
  if (!v) throw new Error("useToast needs a <ToastProvider>");
  return v;
}
