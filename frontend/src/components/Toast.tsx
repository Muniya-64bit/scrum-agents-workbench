import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { IconAlert, IconCheck, IconX } from "./icons";

type ToastKind = "error" | "success";
interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

const ToastContext = createContext<(kind: ToastKind, message: string) => void>(() => {});

/** Show a short message in the corner, e.g. when moving a task fails. */
export function useToast() {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const dismiss = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), []);
  const show = useCallback((kind: ToastKind, message: string) => {
    setToasts((t) => [...t.slice(-2), { id: Date.now() + Math.random(), kind, message }]);
  }, []);

  return (
    <ToastContext.Provider value={show}>
      {children}
      <div className="toasts" aria-live="polite">
        {toasts.map((t) => (
          <ToastItem key={t.id} toast={t} dismiss={dismiss} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastItem({ toast, dismiss }: { toast: Toast; dismiss: (id: number) => void }) {
  useEffect(() => {
    const timer = setTimeout(() => dismiss(toast.id), 5000);
    return () => clearTimeout(timer);
  }, [toast.id, dismiss]);
  return (
    <div className={`toast toast-${toast.kind}`} role={toast.kind === "error" ? "alert" : "status"}>
      {toast.kind === "error" ? <IconAlert /> : <IconCheck />}
      <span>{toast.message}</span>
      <button type="button" className="icon-btn" onClick={() => dismiss(toast.id)} aria-label="Dismiss">
        <IconX size={14} />
      </button>
    </div>
  );
}
