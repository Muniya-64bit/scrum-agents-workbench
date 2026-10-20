import { useState } from "react";

import { api } from "../../api/client";
import type { ProjectMetrics, SprintMetrics } from "../../api/types";
import { delta, pct, pts, type DeltaKind } from "../../lib/format";
import { defaultSprint, definitionOf, previousSprint } from "../../lib/results";
import { useResource } from "../../lib/useResource";
import { BurndownChart } from "../charts/BurndownChart";
import { ErrorState, Loading } from "../ui";
import { KpiTile } from "./KpiTile";
import { Section } from "./Section";

interface Measure {
  label: string;
  /** The sprint field that is shown; also the GQM key of its definition. */
  key: keyof SprintMetrics;
  format: (s: SprintMetrics) => string;
  goodWhenUp: boolean;
  kind: DeltaKind;
  sub?: (s: SprintMetrics) => string;
}

const MEASURES: Measure[] = [
  {
    label: "Velocity",
    key: "completed_points",
    format: (s) => pts(s.completed_points),
    goodWhenUp: true,
    kind: "number",
    sub: (s) => `of ${pts(s.committed_points)} planned`,
  },
  {
    label: "Commitment reliability",
    key: "commitment_reliability",
    format: (s) => pct(s.commitment_reliability),
    goodWhenUp: true,
    kind: "ratio",
  },
  {
    label: "First-pass yield",
    key: "first_pass_yield",
    format: (s) => pct(s.first_pass_yield),
    goodWhenUp: true,
    kind: "ratio",
  },
  {
    label: "Test pass rate",
    key: "test_pass_rate",
    format: (s) => pct(s.test_pass_rate),
    goodWhenUp: true,
    kind: "ratio",
  },
  {
    label: "Open bugs",
    key: "bugs_open_at_end",
    format: (s) => String(s.bugs_open_at_end),
    goodWhenUp: false,
    kind: "number",
    sub: () => "at sprint end",
  },
];

/** One sprint in focus: pick it, read its key measures and its burndown. */
export function SprintDetail({ data, version }: { data: ProjectMetrics; version: number }) {
  const { sprints, gqm } = data;
  const [selected, setSelected] = useState<number | null>(null);
  const sprint = sprints.find((s) => s.sprint_id === selected) ?? defaultSprint(sprints);
  const previous = previousSprint(sprints, sprint);
  const burndown = useResource(() => api.burndown(sprint.sprint_id), [sprint.sprint_id, version]);

  return (
    <Section
      id="detail"
      title="Sprint detail"
      description="Pick a sprint to see its key measures, with the change since the sprint before, and how its open work burned down."
      actions={<SprintSwitch sprints={sprints} current={sprint.sprint_id} onSelect={setSelected} />}
    >
      {sprint.goal && (
        <p className="detail-goal">
          <strong>Sprint {sprint.sprint_number} goal:</strong> {sprint.goal}
        </p>
      )}
      <div className="kpi-grid" role="group" aria-label={`Key measures, sprint ${sprint.sprint_number}`}>
        {MEASURES.map((m) => (
          <KpiTile
            key={m.key}
            label={m.label}
            value={m.format(sprint)}
            definition={definitionOf(gqm, m.key)}
            change={delta(
              sprint[m.key] as number | null,
              previous ? (previous[m.key] as number | null) : null,
              m.goodWhenUp,
              m.kind,
            )}
            changeTitle={previous ? `Change since sprint ${previous.sprint_number}` : undefined}
            sub={m.sub?.(sprint)}
          />
        ))}
      </div>
      <h3 className="detail-subtitle">Burndown</h3>
      <p className="muted results-note">
        Story points still open as stories are completed. The dashed line is the ideal pace.
      </p>
      <div className="results-chart">
        {burndown.error && !burndown.data ? (
          <ErrorState error={burndown.error} onRetry={burndown.reload} />
        ) : !burndown.data ? (
          <Loading label="Loading burndown" />
        ) : (
          <BurndownChart data={burndown.data} />
        )}
      </div>
    </Section>
  );
}

function SprintSwitch({
  sprints,
  current,
  onSelect,
}: {
  sprints: SprintMetrics[];
  current: number;
  onSelect: (id: number) => void;
}) {
  return (
    <div className="sprint-switch" role="group" aria-label="Sprint">
      {sprints.map((s) => (
        <button
          key={s.sprint_id}
          type="button"
          className="sprint-switch-btn"
          aria-pressed={s.sprint_id === current}
          onClick={() => onSelect(s.sprint_id)}
        >
          Sprint {s.sprint_number}
        </button>
      ))}
    </div>
  );
}
