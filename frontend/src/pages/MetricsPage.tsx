import { useState, type ReactNode } from "react";

import { api } from "../api/client";
import type { ProjectMetrics, SprintMetrics } from "../api/types";
import { BarChart } from "../components/charts/BarChart";
import { BurndownChart } from "../components/charts/BurndownChart";
import { PdcaPanel, ReleasesPanel } from "../components/ImprovementPanels";
import { IconChart } from "../components/icons";
import { EmptyState, ErrorState, Loading } from "../components/ui";
import { delta, pct, pts, tokens, usd, type DeltaKind } from "../lib/format";
import { useResource } from "../lib/useResource";
import { useProject } from "./ProjectLayout";

export function MetricsPage() {
  const { project, version } = useProject();
  const res = useResource(() => api.metrics(project.id), [project.id, version]);

  if (res.error && !res.data) return <ErrorState error={res.error} onRetry={res.reload} />;
  if (!res.data) return <Loading label="Loading metrics" />;
  const data = res.data;

  if (data.sprints.length === 0) {
    return (
      <EmptyState icon={<IconChart size={22} />} title="No sprint data yet">
        Metrics appear after sprint planning.
      </EmptyState>
    );
  }

  return (
    <div className="page-body">
      <div>
        <h2 className="section-title">Metrics</h2>
        <p className="muted metrics-intro">
          How the AI Scrum team is doing, measured with Goal-Question-Metric.
        </p>
        <p className="muted metrics-mode">{modeLine(data.project.llm_modes)}</p>
      </div>
      <Kpis data={data} />
      <BurndownPanel sprints={data.sprints} version={version} />
      <VelocityPanel sprints={data.sprints} />
      <QualityPanel sprints={data.sprints} />
      <CostPanel data={data} />
      <GqmPanel data={data} />
      <ReleasesPanel projectId={project.id} version={version} />
      <PdcaPanel projectId={project.id} version={version} />
    </div>
  );
}

function modeLine(modes: string[]): string {
  if (modes.length === 0 || (modes.length === 1 && modes[0] === "mock")) {
    return "Mode: mock — no tokens were spent";
  }
  return `Mode: ${modes.join(", ")}`;
}

// --- 2. KPI tiles --------------------------------------------------------------------------

function Kpis({ data }: { data: ProjectMetrics }) {
  const { sprints, project } = data;
  const closed = sprints.filter((s) => s.closed);
  const latest = closed.length > 0 ? closed[closed.length - 1] : sprints[sprints.length - 1];
  const index = sprints.indexOf(latest);
  const prev = index > 0 ? sprints[index - 1] : undefined;
  const perPoint = project.points_done > 0 ? project.total_cost_usd / project.points_done : null;

  function tile(
    label: string,
    value: string,
    key: keyof SprintMetrics,
    goodWhenUp: boolean,
    kind: DeltaKind,
    sub?: ReactNode,
  ) {
    const curr = latest[key] as number | null;
    const before = prev ? (prev[key] as number | null) : null;
    return <Kpi label={label} value={value} change={delta(curr, before, goodWhenUp, kind)} prev={prev} sub={sub} />;
  }

  return (
    <section className="kpi-grid" aria-label={`Key metrics, sprint ${latest.sprint_number}`}>
      {tile(
        "Velocity",
        pts(latest.completed_points),
        "completed_points",
        true,
        "number",
        `of ${pts(latest.committed_points)} committed`,
      )}
      {tile(
        "Commitment reliability",
        pct(latest.commitment_reliability),
        "commitment_reliability",
        true,
        "ratio",
        `Sprint ${latest.sprint_number}`,
      )}
      {tile("First-pass yield", pct(latest.first_pass_yield), "first_pass_yield", true, "ratio")}
      {tile("Test pass rate", pct(latest.test_pass_rate), "test_pass_rate", true, "ratio")}
      {tile(
        "Open bugs",
        String(latest.bugs_open_at_end),
        "bugs_open_at_end",
        false,
        "number",
        "at sprint end",
      )}
      <Kpi
        label="Est. cost"
        value={usd(project.total_cost_usd)}
        change={null}
        sub={perPoint === null ? "—" : `≈ ${usd(perPoint)} per point`}
      />
    </section>
  );
}

function Kpi({
  label,
  value,
  change,
  prev,
  sub,
}: {
  label: string;
  value: string;
  change: ReturnType<typeof delta>;
  prev?: SprintMetrics;
  sub?: ReactNode;
}) {
  const arrow = change?.direction === "up" ? "▲ " : change?.direction === "down" ? "▼ " : "";
  const tone = change === null || change.good === null ? "flat" : change.good ? "good" : "bad";
  return (
    <div className="kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      <div className="kpi-sub">
        {change && (
          <span
            className={`delta delta-${tone}`}
            title={prev ? `Change since sprint ${prev.sprint_number}` : undefined}
          >
            {arrow}
            {change.text}
          </span>
        )}
        {sub && <span>{sub}</span>}
      </div>
    </div>
  );
}

// --- 3. Burndown ---------------------------------------------------------------------------

function BurndownPanel({ sprints, version }: { sprints: SprintMetrics[]; version: number }) {
  const [selected, setSelected] = useState<number | null>(null);
  const latestId = sprints[sprints.length - 1].sprint_id;
  const sprintId = sprints.some((s) => s.sprint_id === selected) ? (selected as number) : latestId;
  const res = useResource(() => api.burndown(sprintId), [sprintId, version]);

  return (
    <section className="panel metrics-panel" aria-labelledby="burndown-heading">
      <div className="metrics-panel-head">
        <h2 id="burndown-heading" className="metrics-panel-title">
          Burndown
        </h2>
        <select
          className="input select"
          aria-label="Sprint"
          value={sprintId}
          onChange={(e) => setSelected(Number(e.target.value))}
        >
          {sprints.map((s) => (
            <option key={s.sprint_id} value={s.sprint_id}>
              Sprint {s.sprint_number}
            </option>
          ))}
        </select>
      </div>
      {res.error && !res.data ? (
        <ErrorState error={res.error} onRetry={res.reload} />
      ) : !res.data ? (
        <Loading label="Loading burndown" />
      ) : (
        <BurndownChart data={res.data} />
      )}
    </section>
  );
}

// --- 4. Velocity ---------------------------------------------------------------------------

function VelocityPanel({ sprints }: { sprints: SprintMetrics[] }) {
  return (
    <section className="panel metrics-panel" aria-labelledby="velocity-heading">
      <h2 id="velocity-heading" className="metrics-panel-title">
        Velocity
      </h2>
      <BarChart
        title="Committed and completed points per sprint"
        desc="Story points committed at planning next to the points completed, for each sprint"
        unit="points"
        groups={sprints.map((s) => ({
          label: `Sprint ${s.sprint_number}`,
          values: [
            { name: "Committed", value: s.committed_points, tone: "muted" },
            { name: "Completed", value: s.completed_points, tone: "accent" },
          ],
        }))}
      />
    </section>
  );
}

// --- 5. Quality ----------------------------------------------------------------------------

function QualityPanel({ sprints }: { sprints: SprintMetrics[] }) {
  return (
    <section className="panel metrics-panel" aria-labelledby="quality-heading">
      <h2 id="quality-heading" className="metrics-panel-title">
        Quality
      </h2>
      <div className="table-scroll">
        <table className="data-table">
          <caption className="sr-only">Quality metrics per sprint</caption>
          <thead>
            <tr>
              <th scope="col">Sprint</th>
              <th scope="col" className="num">Test runs</th>
              <th scope="col" className="num">Pass rate</th>
              <th scope="col" className="num">First-pass yield</th>
              <th scope="col" className="num">Bugs reported</th>
              <th scope="col" className="num">Fixed</th>
              <th scope="col" className="num">Open at end</th>
              <th scope="col" className="num">Fix attempts</th>
              <th scope="col" className="num">Retry-limit hits</th>
              <th scope="col" className="num">Invalid LLM outputs</th>
            </tr>
          </thead>
          <tbody>
            {sprints.map((s) => (
              <tr key={s.sprint_id}>
                <th scope="row">Sprint {s.sprint_number}</th>
                <td className="num">{s.test_runs}</td>
                <td className="num">{pct(s.test_pass_rate)}</td>
                <td className="num">{pct(s.first_pass_yield)}</td>
                <td className="num">{s.bugs_reported}</td>
                <td className="num">{s.bugs_fixed_in_sprint}</td>
                <td className="num">{s.bugs_open_at_end}</td>
                <td className="num">{s.fix_attempts}</td>
                <td className="num">{s.retry_limit_hits}</td>
                <td className="num">{s.llm_invalid_outputs}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// --- 6. Cost -------------------------------------------------------------------------------

function CostPanel({ data }: { data: ProjectMetrics }) {
  const { sprints, unattributed, project, pricing } = data;
  const cacheHits = sprints.reduce((sum, s) => sum + s.cache_hits, 0);
  return (
    <section className="panel metrics-panel" aria-labelledby="cost-heading">
      <h2 id="cost-heading" className="metrics-panel-title">
        Cost of the AI team
      </h2>
      <div className="table-scroll">
        <table className="data-table">
          <caption className="sr-only">LLM usage and estimated cost per sprint</caption>
          <thead>
            <tr>
              <th scope="col">Sprint</th>
              <th scope="col" className="num">LLM calls</th>
              <th scope="col" className="num">Input tokens</th>
              <th scope="col" className="num">Output tokens</th>
              <th scope="col" className="num">Cache hits</th>
              <th scope="col" className="num">Est. cost</th>
            </tr>
          </thead>
          <tbody>
            {sprints.map((s) => (
              <tr key={s.sprint_id}>
                <th scope="row">Sprint {s.sprint_number}</th>
                <td className="num">{s.llm_calls}</td>
                <td className="num">{tokens(s.input_tokens)}</td>
                <td className="num">{tokens(s.output_tokens)}</td>
                <td className="num">{s.cache_hits}</td>
                <td className="num">{usd(s.est_cost_usd)}</td>
              </tr>
            ))}
            <tr>
              <th scope="row">Backlog &amp; design (before sprint 1)</th>
              <td className="num">{unattributed.llm_calls}</td>
              <td className="num">{tokens(unattributed.input_tokens)}</td>
              <td className="num">{tokens(unattributed.output_tokens)}</td>
              <td className="num">—</td>
              <td className="num">{usd(unattributed.est_cost_usd)}</td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <th scope="row">Total</th>
              <td className="num">{project.total_llm_calls}</td>
              <td className="num">{tokens(project.total_input_tokens)}</td>
              <td className="num">{tokens(project.total_output_tokens)}</td>
              <td className="num">{cacheHits}</td>
              <td className="num">{usd(project.total_cost_usd)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
      <p className="muted metrics-note">
        Estimated from {usd(pricing.input_per_mtok)} per million input tokens and{" "}
        {usd(pricing.output_per_mtok)} per million output tokens ({pricing.model}). {pricing.source}.
      </p>
    </section>
  );
}

// --- 7. GQM --------------------------------------------------------------------------------

function GqmPanel({ data }: { data: ProjectMetrics }) {
  return (
    <section className="panel metrics-panel" aria-labelledby="gqm-heading">
      <h2 id="gqm-heading" className="sr-only">
        Goal-Question-Metric
      </h2>
      <details>
        <summary className="gqm-summary">How these metrics were chosen (GQM)</summary>
        <p className="muted">
          Goal-Question-Metric starts from a goal, asks the questions that show whether we reach it,
          and only then picks the metrics that answer them.
        </p>
        <div className="gqm">
          {data.gqm.map((goal) => (
            <div key={goal.id} className="gqm-goal">
              <h3>
                <span className="gqm-id">{goal.id}</span> {goal.goal}{" "}
                <span className="muted">({goal.viewpoint})</span>
              </h3>
              {goal.questions.map((q) => (
                <div key={q.id} className="gqm-question">
                  <h4>
                    <span className="gqm-id">{q.id}</span> {q.text}
                  </h4>
                  <ul>
                    {q.metrics.map((m) => (
                      <li key={m.key}>
                        <strong>{m.name}</strong> <span className="muted">({m.unit})</span>:{" "}
                        {m.definition}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          ))}
        </div>
      </details>
    </section>
  );
}
