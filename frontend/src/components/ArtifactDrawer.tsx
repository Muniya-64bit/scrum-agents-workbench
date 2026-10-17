import { useEffect, useRef, type KeyboardEvent } from "react";

import { api } from "../api/client";
import { useResource } from "../lib/useResource";
import { useToast } from "./Toast";
import { IconX } from "./icons";
import { Badge, Button, ErrorState, Loading, RoleTag } from "./ui";

const FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

/** Right-side panel that shows one artifact (design note, code, test) with a Copy button. */
export function ArtifactDrawer({
  artifactId,
  onClose,
}: {
  artifactId: number | null;
  onClose: () => void;
}) {
  if (artifactId === null) return null;
  return <Drawer artifactId={artifactId} onClose={onClose} />;
}

function Drawer({ artifactId, onClose }: { artifactId: number; onClose: () => void }) {
  const res = useResource(() => api.artifact(artifactId), [artifactId]);
  const toast = useToast();
  const panel = useRef<HTMLElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const opener = useRef<Element | null>(document.activeElement);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  // Focus the close button on open, give focus back to the opener on close, lock page scroll.
  useEffect(() => {
    const previous = opener.current;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButton.current?.focus();
    return () => {
      document.body.style.overflow = overflow;
      if (previous instanceof HTMLElement) previous.focus();
    };
  }, []);

  useEffect(() => {
    function onKey(e: globalThis.KeyboardEvent) {
      if (e.key === "Escape") onCloseRef.current();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  // Keep Tab inside the dialog.
  function trapFocus(e: KeyboardEvent) {
    if (e.key !== "Tab" || !panel.current) return;
    const items = Array.from(panel.current.querySelectorAll<HTMLElement>(FOCUSABLE));
    if (items.length === 0) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      toast("success", "Copied to clipboard");
    } catch {
      toast("error", "Could not copy to the clipboard");
    }
  }

  const artifact = res.data;
  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} aria-hidden="true" />
      <aside
        ref={panel}
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-title"
        onKeyDown={trapFocus}
      >
        <header className="drawer-header">
          <h2 id="drawer-title" className="drawer-title">
            {artifact ? artifact.name : "Artifact"}
          </h2>
          <button
            ref={closeButton}
            type="button"
            className="icon-btn"
            onClick={onClose}
            aria-label="Close"
          >
            <IconX />
          </button>
        </header>
        <div className="drawer-body">
          {res.error && !artifact ? (
            <ErrorState error={res.error} onRetry={res.reload} />
          ) : !artifact ? (
            <Loading label="Loading artifact" />
          ) : (
            <>
              <div className="drawer-meta">
                <Badge tone="accent">{artifact.kind}</Badge>
                <span className="muted">v{artifact.version}</span>
                <RoleTag role={artifact.created_by} />
              </div>
              {artifact.path && <p className="drawer-path">{artifact.path}</p>}
              {artifact.story_ids.length > 0 && (
                <p className="muted">
                  Linked stories: {artifact.story_ids.map((id) => `#${id}`).join(", ")}
                </p>
              )}
              <div className="drawer-actions">
                <Button onClick={() => copy(artifact.content)}>Copy</Button>
              </div>
              <pre className="code-block">
                <code>{artifact.content}</code>
              </pre>
            </>
          )}
        </div>
      </aside>
    </>
  );
}
