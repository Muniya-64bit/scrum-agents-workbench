import type { ProjectMetrics } from "../../api/types";
import { tokens, usd } from "../../lib/format";
import { isFree } from "../../lib/results";
import { KpiTile } from "./KpiTile";
import { Section } from "./Section";

function costNote(free: boolean, perPoint: number | null): string {
  if (free) return "local model, no per-token price";
  return perPoint === null ? "no points delivered yet" : `≈ ${usd(perPoint)} per point`;
}

/** What the AI team used: a few totals up front, the per-sprint breakdown behind a toggle. */
export function CostSection({ data }: { data: ProjectMetrics }) {
  const { sprints, unattributed, project, pricing } = data;
  const cacheHits = sprints.reduce((sum, s) => sum + s.cache_hits, 0);
  const perPoint = project.points_done > 0 ? project.total_cost_usd / project.points_done : null;
  const free = isFree(pricing);
  return (
    <Section
      id="cost"
      title="Cost of the AI team"
      description="Model calls and tokens used by all agents. Cost is an estimate from the model's token prices."
    >
      <div className="kpi-grid" role="group" aria-label="Cost totals">
        <KpiTile
          label="Model calls"
          value={tokens(project.total_llm_calls)}
          sub={`${cacheHits} answered from cache`}
        />
        <KpiTile
          label="Tokens"
          value={tokens(project.total_input_tokens + project.total_output_tokens)}
          sub={`${tokens(project.total_input_tokens)} in · ${tokens(project.total_output_tokens)} out`}
        />
        <KpiTile
          label="Est. cost"
          value={usd(project.total_cost_usd)}
          sub={costNote(free, perPoint)}
        />
      </div>
      <details className="results-help">
        <summary>Show the breakdown per sprint</summary>
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
      </details>
      <p className="muted results-note">
        {free
          ? `${pricing.model} runs locally and has no per-token price, so its cost is shown as $0.`
          : `Estimated from ${usd(pricing.input_per_mtok)} per million input tokens and ${usd(pricing.output_per_mtok)} per million output tokens (${pricing.model}). ${pricing.source}.`}
      </p>
    </Section>
  );
}
