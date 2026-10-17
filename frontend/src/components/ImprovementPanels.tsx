import { useState } from "react";

import { api } from "../api/client";
import type { ImprovementCheck, ImprovementRow, Release } from "../api/types";
import { delta, pct, pts, usd, type DeltaKind } from "../lib/format";
import { describeDiff, proposedChips } from "../lib/process";
import { parseTime } from "../lib/events";
import { useResource } from "../lib/useResource";
import { ArtifactDrawer } from "./ArtifactDrawer";
import { ErrorState, Loading } from "./ui";

// --- Process improvement (PDCA) -------------------------------------------------------------

const CHECKS: { key: keyof ImprovementCheck; label: string; goodWhenUp: boolean; kind: DeltaKind }[] = [
  { key: "commitment_reliability", label: "Commitment reliability", goodWhenUp: true, kind: "ratio" },
  { key: "first_pass_yield", label: "First-pass yield", goodWhenUp: true, kind: "ratio" },
  { key: "test_pass_rate", label: "Test pass rate", goodWhenUp: true, kind: "ratio" },
  { key: "bugs_reported", label: "Bugs reported", goodWhenUp: false, kind: "number" },
  { key: "fix_attempts", label: "Fix attempts", goodWhenUp: false, kind: "number" },
  { key: "est_cost_usd", label: "Est. cost", goodWhenUp: false, kind: "usd" },
];

function checkValue(key: keyof ImprovementCheck, value: number | null): string {
  if (key === "est_cost_usd") return usd(value ?? 0);
  if (key === "bugs_reported" || key === "fix_attempts") return String(value ?? 0);
  return pct(value);
}

export function PdcaPanel({ projectId, version }: { projectId: number; version: number }) {
  const res = useResource(() => api.improvement(projectId), [projectId, version]);
  return (
    <section className="panel metrics-panel" aria-labelledby="pdca-heading">
      <h2 id="pdca-heading" className="metrics-panel-title">
        Process improvement (PDCA)
      </h2>
      <p className="muted metrics-note pdca-intro">
        Each sprint is one Plan-Do-Check-Act cycle: the retro&apos;s changes become the next
        sprint&apos;s process.
      </p>
      {res.error && !res.data ? (
        <ErrorState error={res.error} onRetry={res.reload} />
      ) : !res.data ? (
        <Loading label="Loading process improvement" />
      ) : (
        <div className="pdca-cards">
          {res.data.map((row) => (
            <PdcaCard key={row.sprint_number} row={row} />
          ))}
        </div>
      )}
    </section>
  );
}

function PdcaCard({ row }: { row: ImprovementRow }) {
  const { plan, act } = row;
  const process = plan.process;
  const applied = describeDiff(plan.changes_applied);
  const proposed = proposedChips(act.proposed_changes);
  const reason = act.proposed_changes.reason;
  return (
    <article className="pdca-card" aria-label={`Sprint ${row.sprint_number}`}>
      <h3 className="pdca-title">Sprint {row.sprint_number}</h3>

      <section className="pdca-block" aria-label="Plan">
        <h4>Plan</h4>
        <p>
          {process.capacity !== undefined ? `Capacity ${process.capacity}` : "Default process"}
          {process.max_fix_retries !== undefined && ` · Fix retries ${process.max_fix_retries}`}
          {process.test_first ? " · Test-first" : ""}
        </p>
        {applied.length > 0 && (
          <ul className="pdca-chips" aria-label="Changed after the last retro">
            {applied.map((c) => (
              <li key={c} className="process-chip">
                {c}
              </li>
            ))}
          </ul>
        )}
        {plan.reason && <p className="muted pdca-reason">{plan.reason}</p>}
      </section>

      <section className="pdca-block" aria-label="Do">
        <h4>Do</h4>
        <p>
          {pts(row.do.committed_points)} committed → {pts(row.do.completed_points)} completed
        </p>
      </section>

      <section className="pdca-block" aria-label="Check">
        <h4>Check</h4>
        <dl className="pdca-checks">
          {CHECKS.map(({ key, label, goodWhenUp, kind }) => {
            const change = row.deltas[key] === null ? null : delta(row.deltas[key], 0, goodWhenUp, kind);
            const arrow = change?.direction === "up" ? "▲ " : change?.direction === "down" ? "▼ " : "";
            const tone = change === null || change.good === null ? "flat" : change.good ? "good" : "bad";
            return (
              <div key={key} className="pdca-check">
                <dt>{label}</dt>
                <dd>
                  {checkValue(key, row.check[key])}
                  {change && (
                    <span className={`delta delta-${tone}`} title="Change since the previous sprint">
                      {" "}
                      {arrow}
                      {change.text}
                    </span>
                  )}
                </dd>
              </div>
            );
          })}
        </dl>
      </section>

      <section className="pdca-block" aria-label="Act">
        <h4>Act</h4>
        {proposed.length > 0 ? (
          <ul className="pdca-chips" aria-label="Proposed for the next sprint">
            {proposed.map((c) => (
              <li key={c} className="process-chip">
                {c}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No process change proposed</p>
        )}
        {reason && <p className="muted pdca-reason">{reason}</p>}
      </section>
    </article>
  );
}

// --- Releases -------------------------------------------------------------------------------

export function ReleasesPanel({ projectId, version }: { projectId: number; version: number }) {
  const res = useResource(() => api.releases(projectId), [projectId, version]);
  const [openId, setOpenId] = useState<number | null>(null);
  const releases: Release[] = res.data ?? [];

  return (
    <section className="panel metrics-panel" aria-labelledby="releases-heading">
      <h2 id="releases-heading" className="metrics-panel-title">
        Releases
      </h2>
      {res.error && !res.data ? (
        <ErrorState error={res.error} onRetry={res.reload} />
      ) : !res.data ? (
        <Loading label="Loading releases" />
      ) : releases.length === 0 ? (
        <p className="muted">No release yet. Each sprint ends with one.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <caption className="sr-only">Releases, one per sprint</caption>
            <thead>
              <tr>
                <th scope="col">Version</th>
                <th scope="col">Sprint</th>
                <th scope="col">Date</th>
                <th scope="col" className="num">Stories</th>
                <th scope="col">Commit</th>
              </tr>
            </thead>
            <tbody>
              {releases.map((r) => (
                <tr key={r.artifact_id}>
                  <th scope="row">
                    <button type="button" className="link-button" onClick={() => setOpenId(r.artifact_id)}>
                      {r.version}
                    </button>
                  </th>
                  <td>{r.sprint_number === null ? "—" : `Sprint ${r.sprint_number}`}</td>
                  <td>{parseTime(r.created_at).toISOString().slice(0, 10)}</td>
                  <td className="num">{r.story_ids.length}</td>
                  <td>
                    <code>{r.sha.slice(0, 7)}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <ArtifactDrawer artifactId={openId} onClose={() => setOpenId(null)} />
    </section>
  );
}
