import type { ProjectMetrics } from "../../api/types";
import { pct } from "../../lib/format";
import { modeLine, summarizeOutcome, type VerdictTone } from "../../lib/results";
import { Badge, type Tone } from "../ui";

const VERDICT_TONE: Record<VerdictTone, Tone> = { good: "done", warn: "testing", bad: "danger" };

/** The answer first: what the project delivered, then the numbers behind it. */
export function OutcomeSummary({ data }: { data: ProjectMetrics }) {
  const o = summarizeOutcome(data);
  return (
    <section className="panel outcome" aria-labelledby="outcome-title">
      <div className="outcome-head">
        <h2 id="outcome-title" className="results-section-title">
          Project outcome
        </h2>
        <Badge tone={VERDICT_TONE[o.verdict.tone]}>{o.verdict.label}</Badge>
      </div>
      <p className="outcome-verdict">{o.verdict.text}</p>
      <dl className="outcome-stats">
        <Stat label="Stories done" value={`${o.storiesDone} of ${o.storiesTotal}`} />
        <Stat label="Points delivered" value={`${o.pointsDone} of ${o.pointsTotal}`} />
        <Stat label="Sprints run" value={String(o.sprintCount)} />
        <Stat label="Test pass rate" value={pct(o.testPassRate)} hint="latest sprint with tests" />
        <Stat label="Open bugs" value={String(o.openBugs)} hint="at the end of the last sprint" />
        <Stat label="Lines of code" value={String(o.linesOfCode)} hint="generated app" />
      </dl>
      <p className="muted outcome-mode">{modeLine(data)}</p>
    </section>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="outcome-stat">
      <dt>{label}</dt>
      <dd>{value}</dd>
      {hint && <span className="outcome-hint">{hint}</span>}
    </div>
  );
}
