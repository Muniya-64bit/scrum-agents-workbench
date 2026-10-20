import { api } from "../api/client";
import { CostSection } from "../components/results/CostSection";
import { GqmSection } from "../components/results/GqmSection";
import { OutcomeSummary } from "../components/results/OutcomeSummary";
import { QualityTable } from "../components/results/QualityTable";
import { SprintComparison } from "../components/results/SprintComparison";
import { SprintDetail } from "../components/results/SprintDetail";
import { IconChart } from "../components/icons";
import { PdcaPanel, ReleasesPanel } from "../components/ImprovementPanels";
import { EmptyState, ErrorState, Loading } from "../components/ui";
import { useResource } from "../lib/useResource";
import { useProject } from "./ProjectLayout";

/** Jump links, in page order, so a long results page stays easy to move around in. */
const SECTIONS = [
  { id: "sprints", label: "Sprints" },
  { id: "detail", label: "Sprint detail" },
  { id: "quality", label: "Quality" },
  { id: "cost", label: "Cost" },
  { id: "releases", label: "Releases" },
  { id: "improvement", label: "Improvement" },
  { id: "method", label: "Method" },
];

/** The results of the project: what was delivered, sprint by sprint, how well, at what cost. */
export function MetricsPage() {
  const { project, version } = useProject();
  const res = useResource(() => api.metrics(project.id), [project.id, version]);

  if (res.error && !res.data) return <ErrorState error={res.error} onRetry={res.reload} />;
  if (!res.data) return <Loading label="Loading results" />;
  const data = res.data;

  if (data.sprints.length === 0) {
    return (
      <EmptyState icon={<IconChart size={22} />} title="No sprint data yet">
        Results appear after sprint planning.
      </EmptyState>
    );
  }

  return (
    <div className="page-body">
      <h2 className="section-title">Results</h2>
      <OutcomeSummary data={data} />
      <nav className="results-nav" aria-label="On this page">
        {SECTIONS.map((s) => (
          <a key={s.id} href={`#${s.id}`}>
            {s.label}
          </a>
        ))}
      </nav>
      <SprintComparison sprints={data.sprints} />
      <SprintDetail data={data} version={version} />
      <QualityTable sprints={data.sprints} gqm={data.gqm} />
      <CostSection data={data} />
      <ReleasesPanel projectId={project.id} version={version} />
      <PdcaPanel projectId={project.id} version={version} />
      <GqmSection gqm={data.gqm} />
    </div>
  );
}
