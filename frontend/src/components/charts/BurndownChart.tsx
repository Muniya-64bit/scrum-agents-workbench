import { useState } from "react";

import type { Burndown, BurndownPoint } from "../../api/types";
import { duration } from "../../lib/format";
import { ChartFrame, PLOT, VIEW, niceTicks, yPos } from "./ChartFrame";

/** Points still open over time against an ideal line. Plots seconds, or steps for instant runs. */
export function BurndownChart({ data }: { data: Burndown }) {
  const [active, setActive] = useState<number | null>(null);
  const { series } = data;

  if (series.length < 2) {
    return <p className="muted chart-empty">No progress recorded yet</p>;
  }

  const byTime = data.duration_s >= 1;
  const xOf = (p: BurndownPoint) => (byTime ? p.t : p.step);
  const last = series[series.length - 1];
  const xMax = Math.max(byTime ? Math.max(data.duration_s, last.t) : last.step, 1e-3);
  const px = (x: number) => PLOT.x0 + (x / xMax) * (PLOT.x1 - PLOT.x0);

  const top = Math.max(data.committed_points, ...series.map((p) => p.remaining), 1);
  const ticks = niceTicks(top, 4);
  const yMax = ticks[ticks.length - 1];
  const py = (v: number) => yPos(v, yMax);

  // Step-after line: hold the old value until the moment of change, then drop.
  const path = series
    .map((p, i) => (i === 0 ? `M${px(xOf(p))},${py(p.remaining)}` : `H${px(xOf(p))}V${py(p.remaining)}`))
    .join("");
  const ideal = `M${px(0)},${py(data.committed_points)}L${px(xMax)},${py(0)}`;
  const xLabel = (x: number) => (byTime ? duration(x) : String(Math.round(x)));
  const xTicks = [0, xMax / 2, xMax];

  const shown = active === null ? null : series[active];
  const when = (p: BurndownPoint) => (byTime ? duration(p.t) : `step ${p.step}`);

  return (
    <div className="chart">
      <ChartFrame
        title={`Burndown, sprint ${data.sprint_number}`}
        desc={`Sprint ${data.sprint_number}: ${data.committed_points} committed, ${data.remaining_points} left`}
        yTicks={ticks}
        yLabel="points left"
      >
        {xTicks.map((x, i) => (
          <text
            key={i}
            x={px(x)}
            y={PLOT.y1 + 16}
            fontSize={11}
            fill="var(--text-muted)"
            textAnchor={i === 0 ? "start" : i === 2 ? "end" : "middle"}
          >
            {xLabel(x)}
          </text>
        ))}
        <text x={PLOT.x1} y={VIEW.height - 4} fontSize={11} fill="var(--text-muted)" textAnchor="end">
          {byTime ? "time since sprint start" : "steps"}
        </text>
        <path d={ideal} fill="none" stroke="var(--text-subtle)" strokeWidth={1.5} strokeDasharray="5 4" />
        <path d={path} fill="none" stroke="var(--accent)" strokeWidth={2} />
        {series.map((p, i) => (
          <g
            key={i}
            tabIndex={0}
            className="chart-point"
            onMouseEnter={() => setActive(i)}
            onMouseLeave={() => setActive((a) => (a === i ? null : a))}
            onFocus={() => setActive(i)}
            onBlur={() => setActive((a) => (a === i ? null : a))}
          >
            <title>{`${p.label}: ${p.remaining} points left at ${when(p)}`}</title>
            <circle cx={px(xOf(p))} cy={py(p.remaining)} r={4} fill="var(--accent)" />
          </g>
        ))}
      </ChartFrame>
      {shown && (
        <div
          role="tooltip"
          className="chart-tooltip"
          style={{
            left: `${(px(xOf(shown)) / VIEW.width) * 100}%`,
            top: `${(py(shown.remaining) / VIEW.height) * 100}%`,
          }}
        >
          <strong>{shown.label}</strong>
          <span>{shown.remaining} points left</span>
          <span>{when(shown)}</span>
        </div>
      )}
      <ul className="legend" aria-label="Legend">
        <li>
          <span className="swatch swatch-line" style={{ background: "var(--accent)" }} /> Actual
        </li>
        <li>
          <span className="swatch swatch-dash" /> Ideal
        </li>
      </ul>
    </div>
  );
}
