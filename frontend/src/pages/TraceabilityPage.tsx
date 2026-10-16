import { useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import type { TraceItem, TraceRow } from "../api/types";
import { ArtifactDrawer } from "../components/ArtifactDrawer";
import { IconAlert, IconLink } from "../components/icons";
import { Badge, EmptyState, ErrorState, Loading } from "../components/ui";
import { pct } from "../lib/format";
import { useResource } from "../lib/useResource";
import { useProject } from "./ProjectLayout";

const KIND_LABEL: Record<string, string> = {
  architecture: "ARC",
  diagram: "DIA",
  api_spec: "API",
  design: "DES",
  code: "CODE",
  test: "TEST",
  release: "REL",
};

const kindLabel = (kind: string) => KIND_LABEL[kind] ?? kind.slice(0, 4).toUpperCase();

/** What a planned story still lacks, e.g. "design, test"; empty when it is complete. */
function missing(row: TraceRow): string {
  const gaps: string[] = [];
  if (row.design.length === 0) gaps.push("design");
  if (row.code.length === 0) gaps.push("code");
  if (row.test.length === 0) gaps.push("test");
  return gaps.join(", ");
}

export function TraceabilityPage() {
  const { project, version } = useProject();
  const res = useResource(() => api.traceability(project.id), [project.id, version]);
  const [params, setParams] = useSearchParams();
  const [openId, setOpenId] = useState<number | null>(null);

  if (res.error && !res.data) return <ErrorState error={res.error} onRetry={res.reload} />;
  if (!res.data) return <Loading label="Loading traceability" />;
  const rows = res.data;
  if (rows.length === 0) {
    return (
      <EmptyState icon={<IconLink size={22} />} title="No stories yet">
        The matrix fills in as the Product Owner writes stories and the other agents add design,
        code and tests.
      </EmptyState>
    );
  }

  const sprint = params.get("sprint") ?? "all";
  const status = params.get("status") ?? "all";
  const gapsOnly = params.get("gaps") === "1";
  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value === null || value === "all") next.delete(key);
    else next.set(key, value);
    setParams(next, { replace: true });
  };

  const planned = rows.filter((r) => r.sprint_number !== null);
  const acTotal = rows.reduce((sum, r) => sum + r.ac_count, 0);
  const acCovered = rows.reduce((sum, r) => sum + Math.min(r.test_count, r.ac_count), 0);
  const sprintNumbers = [...new Set(planned.map((r) => r.sprint_number as number))].sort(
    (a, b) => a - b,
  );

  const shown = rows.filter((r) => {
    if (sprint === "none" ? r.sprint_number !== null : sprint !== "all" && r.sprint_number !== Number(sprint)) {
      return false;
    }
    if (status !== "all" && r.status !== status) return false;
    if (gapsOnly && (r.sprint_number === null || r.complete)) return false;
    return true;
  });

  return (
    <div className="page-body">
      <dl className="stats">
        <Stat
          label="Trace completeness"
          value={pct(planned.length ? planned.filter((r) => r.complete).length / planned.length : null)}
        />
        <Stat label="Stories with failing tests" value={rows.filter((r) => r.last_test_ok === false).length} />
        <Stat label="Open bugs" value={rows.reduce((sum, r) => sum + r.open_bugs, 0)} />
        <Stat label="AC coverage" value={pct(acTotal ? acCovered / acTotal : null)} />
      </dl>

      <div className="filter-bar">
        <label className="filter">
          Sprint
          <select
            className="input select"
            value={sprint}
            onChange={(e) => setParam("sprint", e.target.value)}
          >
            <option value="all">All sprints</option>
            {sprintNumbers.map((n) => (
              <option key={n} value={String(n)}>
                Sprint {n}
              </option>
            ))}
            <option value="none">Not planned</option>
          </select>
        </label>
        <label className="filter">
          Status
          <select
            className="input select"
            value={status}
            onChange={(e) => setParam("status", e.target.value)}
          >
            <option value="all">All statuses</option>
            <option value="backlog">Backlog</option>
            <option value="sprint">In sprint</option>
            <option value="done">Done</option>
          </select>
        </label>
        <label className="filter filter-check">
          <input
            type="checkbox"
            checked={gapsOnly}
            onChange={(e) => setParam("gaps", e.target.checked ? "1" : null)}
          />
          Gaps only
        </label>
      </div>

      <section className="panel" aria-label="Traceability matrix">
        <div className="table-scroll">
          <table className="data-table trace-table">
            <caption className="sr-only">
              Traceability from user story to design, code and tests
            </caption>
            <thead>
              <tr>
                <th scope="col">Story</th>
                <th scope="col">Design</th>
                <th scope="col">Code</th>
                <th scope="col">Tests</th>
                <th scope="col">Result</th>
                <th scope="col" className="num">
                  AC → tests
                </th>
              </tr>
            </thead>
            <tbody>
              {shown.length === 0 && (
                <tr>
                  <td colSpan={6} className="muted trace-none">
                    No stories match these filters.
                  </td>
                </tr>
              )}
              {shown.map((row) => (
                <TraceRowView key={row.story_id} row={row} onOpen={setOpenId} />
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <ArtifactDrawer artifactId={openId} onClose={() => setOpenId(null)} />
    </div>
  );
}

function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="stat">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function TraceRowView({ row, onOpen }: { row: TraceRow; onOpen: (id: number) => void }) {
  const gap = row.sprint_number !== null && !row.complete ? missing(row) : "";
  const gapId = `gap-${row.story_id}`;
  return (
    <tr>
      <th scope="row" className="trace-story" aria-describedby={gap ? gapId : undefined}>
        <div className="trace-story-line">
          <span className="story-id">#{row.story_id}</span>
          <span className="trace-title">{row.title}</span>
          {gap && (
            <>
              <span className="trace-gap" title={`Missing: ${gap}`}>
                <IconAlert size={14} />
              </span>
              <span id={gapId} className="sr-only">
                Missing: {gap}
              </span>
            </>
          )}
        </div>
        <div className="trace-story-meta">
          <Badge tone={row.status === "backlog" ? "neutral" : "doing"}>{row.status}</Badge>
          {row.sprint_number !== null && <span className="muted">Sprint {row.sprint_number}</span>}
        </div>
      </th>
      <td>
        <Chips items={row.design} onOpen={onOpen} />
      </td>
      <td>
        <Chips items={row.code} onOpen={onOpen} />
      </td>
      <td>
        <Chips items={row.test} onOpen={onOpen} />
      </td>
      <td>
        <Result row={row} />
      </td>
      <td className="num" title="test functions / acceptance criteria">
        {row.ac_count > 0 ? `${Math.min(row.test_count, row.ac_count)}/${row.ac_count}` : "—"}
      </td>
    </tr>
  );
}

function Chips({ items, onOpen }: { items: TraceItem[]; onOpen: (id: number) => void }) {
  if (items.length === 0) return <span className="muted">—</span>;
  return (
    <div className="chips">
      {items.map((it) => (
        <button
          key={it.artifact_id}
          type="button"
          className="artifact-chip"
          onClick={() => onOpen(it.artifact_id)}
        >
          <span className="artifact-kind">{kindLabel(it.kind)}</span>
          <span className="artifact-name">
            {it.name}
            {it.version > 1 ? ` v${it.version}` : ""}
          </span>
        </button>
      ))}
    </div>
  );
}

function Result({ row }: { row: TraceRow }) {
  return (
    <div className="trace-result">
      {row.last_test_ok === null ? (
        <Badge>Not run</Badge>
      ) : (
        <>
          <Badge tone="done">{row.tests_passed} passed</Badge>
          {row.tests_failed > 0 && <Badge tone="danger">{row.tests_failed} failed</Badge>}
        </>
      )}
      {row.open_bugs > 0 && (
        <Badge tone="danger">
          {row.open_bugs} open {row.open_bugs === 1 ? "bug" : "bugs"}
        </Badge>
      )}
    </div>
  );
}
