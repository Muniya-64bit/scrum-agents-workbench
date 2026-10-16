import { useEffect } from "react";

const EVENT = "workbench:projects-changed";

/** Tell listeners (e.g. the sidebar's inbox count) that a project's phase or gate changed. */
export function notifyProjectsChanged(): void {
  window.dispatchEvent(new Event(EVENT));
}

export function useOnProjectsChanged(fn: () => void): void {
  useEffect(() => {
    window.addEventListener(EVENT, fn);
    return () => window.removeEventListener(EVENT, fn);
  }, [fn]);
}
