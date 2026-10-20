import type { SprintMetrics } from "../../api/types";
import { pct, pts } from "../../lib/format";
import { meterRows } from "../../lib/results";
import { BarChart } from "../charts/BarChart";
import { Section } from "./Section";

/** Every sprint side by side: what was planned, what was completed, what was carried over. */
export function SprintComparison({ sprints }: { sprints: SprintMetrics[] }) {
  const rows = meterRows(sprints);
  return (
    <Section
      id="sprints"
      title="Sprint by sprint"
      description="What each sprint planned at sprint planning and what it completed by the end. A story is completed when all its tasks are done."
    >
      <p className="meter-legend" aria-hidden="true">
        <span className="meter-key meter-key-planned" /> Planned
        <span className="meter-key meter-key-done" /> Completed
      </p>
      <div className="table-scroll">
        <table className="data-table">
          <caption className="sr-only">Planned and completed work for every sprint</caption>
          <thead>
            <tr>
              <th scope="col">Sprint</th>
              <th scope="col" className="num">Planned</th>
              <th scope="col" className="num">Completed</th>
              <th scope="col" className="meter-col">Points</th>
              <th scope="col" className="num">Carried over</th>
              <th scope="col" className="num">Reliability</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ sprint: s, plannedWidth, completedWidth }) => (
              <tr key={s.sprint_id}>
                <th scope="row">
                  Sprint {s.sprint_number}
                  {s.goal && <span className="row-note">{s.goal}</span>}
                </th>
                <td className="num">
                  {s.committed_stories} {s.committed_stories === 1 ? "story" : "stories"} ·{" "}
                  {pts(s.committed_points)}
                </td>
                <td className="num">
                  {s.completed_stories} {s.completed_stories === 1 ? "story" : "stories"} ·{" "}
                  {pts(s.completed_points)}
                </td>
                <td className="meter-col">
                  <div className="meter" aria-hidden="true">
                    <div className="meter-planned" style={{ width: `${plannedWidth}%` }} />
                    <div className="meter-done" style={{ width: `${completedWidth}%` }} />
                  </div>
                </td>
                <td className="num">{s.carried_over_stories}</td>
                <td className="num">{pct(s.commitment_reliability)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {sprints.length > 1 && (
        <div className="results-chart">
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
        </div>
      )}
    </Section>
  );
}
