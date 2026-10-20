import { useState } from "react";

import type { GqmGoal, SprintMetrics } from "../../api/types";
import { pct } from "../../lib/format";
import { definitionOf } from "../../lib/results";
import { Button } from "../ui";
import { Section } from "./Section";

interface Column {
  /** The GQM metric key, which also gives the column its definition. */
  key: string;
  label: string;
  value: (s: SprintMetrics) => string;
  /** Shown only after "Show all columns": useful for debugging the agents, not for a summary. */
  detail?: boolean;
}

const count = (n: number) => String(n);

const COLUMNS: Column[] = [
  { key: "test_runs", label: "Test runs", value: (s) => count(s.test_runs) },
  { key: "test_pass_rate", label: "Pass rate", value: (s) => pct(s.test_pass_rate) },
  { key: "first_pass_yield", label: "First-pass yield", value: (s) => pct(s.first_pass_yield) },
  { key: "bugs_reported", label: "Bugs reported", value: (s) => count(s.bugs_reported) },
  { key: "bugs_fixed_in_sprint", label: "Fixed", value: (s) => count(s.bugs_fixed_in_sprint) },
  { key: "bugs_open_at_end", label: "Open at end", value: (s) => count(s.bugs_open_at_end) },
  { key: "fix_attempts", label: "Fix attempts", value: (s) => count(s.fix_attempts), detail: true },
  {
    key: "retry_limit_hits",
    label: "Retry-limit hits",
    value: (s) => count(s.retry_limit_hits),
    detail: true,
  },
  {
    key: "llm_invalid_outputs",
    label: "Invalid model outputs",
    value: (s) => count(s.llm_invalid_outputs),
    detail: true,
  },
];

/** Test results and bugs for every sprint, with the meaning of each column one click away. */
export function QualityTable({ sprints, gqm }: { sprints: SprintMetrics[]; gqm: GqmGoal[] }) {
  const [showAll, setShowAll] = useState(false);
  const columns = COLUMNS.filter((c) => showAll || !c.detail);
  return (
    <Section
      id="quality"
      title="Quality"
      description="How well the generated code passed its tests, and how many bugs QA found and the Developer fixed."
      actions={
        <Button aria-expanded={showAll} onClick={() => setShowAll((v) => !v)}>
          {showAll ? "Show fewer columns" : "Show all columns"}
        </Button>
      }
    >
      <div className="table-scroll">
        <table className="data-table">
          <caption className="sr-only">Quality metrics per sprint</caption>
          <thead>
            <tr>
              <th scope="col">Sprint</th>
              {columns.map((c) => (
                <th key={c.key} scope="col" className="num" title={definitionOf(gqm, c.key)}>
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sprints.map((s) => (
              <tr key={s.sprint_id}>
                <th scope="row">Sprint {s.sprint_number}</th>
                {columns.map((c) => (
                  <td key={c.key} className="num">
                    {c.value(s)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details className="results-help">
        <summary>What do these columns mean?</summary>
        <dl className="definition-list">
          {columns.map((c) => (
            <div key={c.key}>
              <dt>{c.label}</dt>
              <dd>{definitionOf(gqm, c.key)}</dd>
            </div>
          ))}
        </dl>
      </details>
    </Section>
  );
}
