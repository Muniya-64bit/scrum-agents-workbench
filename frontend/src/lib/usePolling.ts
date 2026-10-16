import { useEffect } from "react";

/** Call `fn` every `ms` while the tab is visible, and again when the tab gets focus. */
export function usePolling(fn: () => void, ms: number): void {
  useEffect(() => {
    const tick = () => {
      if (document.visibilityState === "visible") fn();
    };
    const id = setInterval(tick, ms);
    window.addEventListener("focus", fn);
    return () => {
      clearInterval(id);
      window.removeEventListener("focus", fn);
    };
  }, [fn, ms]);
}
