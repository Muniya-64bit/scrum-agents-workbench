import { useId, type ReactNode } from "react";

/** Fixed drawing area; the SVG scales to its container with `width="100%"`. */
export const VIEW = { width: 560, height: 240 };
export const MARGIN = { left: 44, right: 16, top: 16, bottom: 36 };
export const PLOT = {
  x0: MARGIN.left,
  x1: VIEW.width - MARGIN.right,
  y0: MARGIN.top,
  y1: VIEW.height - MARGIN.bottom,
};

/** Round tick values from 0 up to a "nice" maximum that is at least `max`. */
export function niceTicks(max: number, count = 4): number[] {
  if (!(max > 0)) return [0, 1];
  const rough = max / count;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const norm = rough / magnitude;
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10) * magnitude;
  const ticks = [0];
  while (ticks[ticks.length - 1] < max - 1e-9) {
    ticks.push(Number((ticks[ticks.length - 1] + step).toFixed(10)));
  }
  return ticks;
}

/** Vertical position of `value` on a 0..yMax axis. */
export function yPos(value: number, yMax: number): number {
  return PLOT.y1 - (yMax > 0 ? value / yMax : 0) * (PLOT.y1 - PLOT.y0);
}

/** Axes and gridlines shared by the charts. Children draw inside the plot area. */
export function ChartFrame({
  title,
  desc,
  yTicks,
  yLabel,
  children,
}: {
  title: string;
  desc: string;
  yTicks: number[];
  yLabel?: string;
  children: ReactNode;
}) {
  const uid = useId();
  const titleId = `${uid}-title`;
  const descId = `${uid}-desc`;
  const yMax = yTicks[yTicks.length - 1] || 1;
  return (
    <svg
      className="chart-svg"
      viewBox={`0 0 ${VIEW.width} ${VIEW.height}`}
      width="100%"
      role="img"
      aria-labelledby={`${titleId} ${descId}`}
    >
      <title id={titleId}>{title}</title>
      <desc id={descId}>{desc}</desc>
      {yTicks.map((tick) => (
        <g key={tick}>
          <line
            x1={PLOT.x0}
            x2={PLOT.x1}
            y1={yPos(tick, yMax)}
            y2={yPos(tick, yMax)}
            stroke="var(--border)"
            strokeWidth={1}
          />
          <text
            x={PLOT.x0 - 8}
            y={yPos(tick, yMax) + 4}
            textAnchor="end"
            fontSize={11}
            fill="var(--text-muted)"
          >
            {tick}
          </text>
        </g>
      ))}
      {yLabel && (
        <text x={PLOT.x0} y={PLOT.y0 - 5} fontSize={11} fill="var(--text-muted)">
          {yLabel}
        </text>
      )}
      <line
        x1={PLOT.x0}
        x2={PLOT.x1}
        y1={PLOT.y1}
        y2={PLOT.y1}
        stroke="var(--border-strong)"
        strokeWidth={1}
      />
      {children}
    </svg>
  );
}
