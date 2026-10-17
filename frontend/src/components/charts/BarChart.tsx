import { useState } from "react";

import { ChartFrame, PLOT, niceTicks, yPos } from "./ChartFrame";

export type BarTone = "muted" | "accent" | "done";

export interface BarGroup {
  label: string;
  values: { name: string; value: number; tone: BarTone }[];
}

const FILL: Record<BarTone, string> = {
  muted: "var(--border-strong)",
  accent: "var(--accent)",
  done: "var(--status-done)",
};

/** Grouped vertical bars with value labels, a legend and keyboard-focusable bars. */
export function BarChart({
  groups,
  unit,
  title,
  desc,
}: {
  groups: BarGroup[];
  unit: string;
  title: string;
  desc: string;
}) {
  const [active, setActive] = useState<string | null>(null);
  const max = Math.max(1, ...groups.flatMap((g) => g.values.map((v) => v.value)));
  const ticks = niceTicks(max, 4);
  const yMax = ticks[ticks.length - 1];
  const groupWidth = (PLOT.x1 - PLOT.x0) / Math.max(groups.length, 1);
  const legend = new Map<string, BarTone>();
  groups.forEach((g) => g.values.forEach((v) => legend.set(v.name, v.tone)));

  return (
    <div className="chart">
      <ChartFrame title={title} desc={desc} yTicks={ticks} yLabel={unit}>
        {groups.map((g, gi) => {
          const barWidth = Math.min(36, (groupWidth * 0.7) / Math.max(g.values.length, 1));
          const start = PLOT.x0 + gi * groupWidth + (groupWidth - barWidth * g.values.length) / 2;
          return (
            <g key={g.label}>
              {g.values.map((v, vi) => {
                const x = start + vi * barWidth;
                const y = yPos(v.value, yMax);
                const id = `${g.label}/${v.name}`;
                return (
                  <g
                    key={v.name}
                    tabIndex={0}
                    className="chart-point"
                    onMouseEnter={() => setActive(id)}
                    onMouseLeave={() => setActive((a) => (a === id ? null : a))}
                    onFocus={() => setActive(id)}
                    onBlur={() => setActive((a) => (a === id ? null : a))}
                  >
                    <title>{`${g.label}, ${v.name}: ${v.value} ${unit}`}</title>
                    <rect
                      x={x + 2}
                      y={y}
                      width={Math.max(barWidth - 4, 1)}
                      height={Math.max(PLOT.y1 - y, 0)}
                      rx={3}
                      fill={FILL[v.tone]}
                      opacity={active && active !== id ? 0.55 : 1}
                    />
                    <text x={x + barWidth / 2} y={y - 5} textAnchor="middle" fontSize={11} fill="var(--text)">
                      {v.value}
                    </text>
                  </g>
                );
              })}
              <text
                x={PLOT.x0 + gi * groupWidth + groupWidth / 2}
                y={PLOT.y1 + 16}
                textAnchor="middle"
                fontSize={11}
                fill="var(--text-muted)"
              >
                {g.label}
              </text>
            </g>
          );
        })}
      </ChartFrame>
      <ul className="legend" aria-label="Legend">
        {[...legend].map(([name, tone]) => (
          <li key={name}>
            <span className="swatch" style={{ background: FILL[tone] }} /> {name}
          </li>
        ))}
      </ul>
    </div>
  );
}
