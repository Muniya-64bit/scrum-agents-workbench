import { useState, type FormEvent } from "react";

import { api } from "../api/client";
import type { Project } from "../api/types";
import { useToast } from "./Toast";
import { Button } from "./ui";

const POINTS = [1, 2, 3, 5];

/**
 * After the release: report a problem found in the product. It becomes a top-priority fix story and
 * the project offers a maintenance sprint. Shown only on a finished project.
 */
export function MaintenancePanel({ project, onDone }: { project: Project; onDone: (p: Project) => void }) {
  const toast = useToast();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [points, setPoints] = useState(2);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const next = await api.requestMaintenance(project.id, {
        title: title.trim(),
        description: description.trim(),
        points,
      });
      toast("success", "The fix is in the backlog. Start sprint planning to work on it.");
      setTitle("");
      setDescription("");
      onDone(next);
    } catch (err) {
      toast("error", err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel maintenance" aria-labelledby="maintenance-title">
      <details>
        <summary id="maintenance-title" className="maintenance-summary">
          Found a problem after the release?
        </summary>
        <p className="muted maintenance-intro">
          Describe it. It becomes a top-priority fix story, and the next sprint plans it.
        </p>
        <form onSubmit={submit} className="maintenance-form">
          <label className="field">
            <span className="field-label">Problem</span>
            <input
              className="input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Empty title is accepted"
              minLength={3}
              maxLength={120}
              required
            />
          </label>
          <label className="field">
            <span className="field-label">What happens</span>
            <textarea
              className="input textarea"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Creating an item with an empty title returns 201 instead of 422."
              rows={3}
              minLength={3}
              maxLength={1000}
              required
            />
          </label>
          <label className="field maintenance-points">
            <span className="field-label">Size (points)</span>
            <select
              className="input select"
              value={points}
              onChange={(e) => setPoints(Number(e.target.value))}
            >
              {POINTS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
          <div>
            <Button variant="primary" type="submit" loading={busy}>
              Request a fix
            </Button>
          </div>
        </form>
      </details>
    </section>
  );
}
