import type { ReactNode } from "react";

import type { Delta } from "../../lib/format";

/** One headline number with its change since the previous sprint and what it measures. */
export function KpiTile({
  label,
  value,
  definition,
  change,
  changeTitle,
  sub,
}: {
  label: string;
  value: string;
  definition?: string;
  change?: Delta | null;
  changeTitle?: string;
  sub?: ReactNode;
}) {
  const arrow = change?.direction === "up" ? "▲ " : change?.direction === "down" ? "▼ " : "";
  const tone = !change || change.good === null ? "flat" : change.good ? "good" : "bad";
  return (
    <div className="kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      <div className="kpi-sub">
        {change && (
          <span className={`delta delta-${tone}`} title={changeTitle}>
            {arrow}
            {change.text}
          </span>
        )}
        {sub && <span>{sub}</span>}
      </div>
      {definition && <p className="kpi-def">{definition}</p>}
    </div>
  );
}
