// Number formatting for the metrics pages. All helpers are pure and never throw.

const MINUS = "−";

/** Ratio as a percentage with one decimal: 0.625 -> "62.5%"; null -> "—". */
export function pct(ratio: number | null | undefined): string {
  return ratio === null || ratio === undefined ? "—" : `${(ratio * 100).toFixed(1)}%`;
}

export function pts(n: number): string {
  return `${n} pt`;
}

/** Money: 4 decimals below $1 (token costs are tiny), 2 decimals from $1 up. */
export function usd(n: number): string {
  return `$${Math.abs(n) < 1 ? n.toFixed(4) : n.toFixed(2)}`;
}

export function tokens(n: number): string {
  return n.toLocaleString("en-US");
}

export type DeltaKind = "number" | "ratio" | "usd";

export interface Delta {
  text: string;
  direction: "up" | "down" | "flat";
  /** True when the change is an improvement, false when it is a regression, null when flat. */
  good: boolean | null;
}

/** Change from `prev` to `curr`. Ratios are shown in percentage points ("pp"). */
export function delta(
  curr: number | null,
  prev: number | null,
  goodWhenUp: boolean,
  kind: DeltaKind = "number",
): Delta | null {
  if (curr === null || prev === null) return null;
  const diff = kind === "ratio" ? (curr - prev) * 100 : curr - prev;
  const places = kind === "usd" ? 4 : kind === "ratio" ? 1 : Number.isInteger(diff) ? 0 : 2;
  const rounded = Number(Math.abs(diff).toFixed(places));
  if (rounded === 0) return { text: "±0", direction: "flat", good: null };
  const up = diff > 0;
  const sign = up ? "+" : MINUS;
  const body =
    kind === "usd"
      ? usd(rounded)
      : kind === "ratio"
        ? `${rounded.toFixed(1)} pp`
        : rounded.toFixed(places);
  return { text: `${sign}${body}`, direction: up ? "up" : "down", good: up === goodWhenUp };
}

/** Seconds as "45s" or "2m 05s". */
export function duration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  if (total < 60) return `${total}s`;
  return `${Math.floor(total / 60)}m ${String(total % 60).padStart(2, "0")}s`;
}

/** A file name stem from a project name: "Todo app" -> "todo-app". */
export function slugify(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "project";
}
