import { api } from "../api/client";
import type { Project } from "../api/types";
import { ApprovalCard } from "../components/ApprovalCard";
import { IconCheck } from "../components/icons";
import { EmptyState, ErrorState, Loading } from "../components/ui";
import { notifyProjectsChanged } from "../lib/projectsChanged";
import { useResource } from "../lib/useResource";
import { usePolling } from "../lib/usePolling";

/** Every project waiting at a gate, across all projects, with what to approve. */
export function InboxPage() {
  const projects = useResource(() => api.listProjects(), []);
  usePolling(projects.reload, 10_000);
  const waiting = projects.data?.filter((p) => p.awaiting_approval) ?? [];

  const done = (p: Project) => {
    projects.setData((list) => list?.map((x) => (x.id === p.id ? p : x)));
    notifyProjectsChanged();
  };

  return (
    <div className="page">
      <header className="page-header">
        <div className="page-header-row">
          <div className="page-title-block">
            <h1 className="page-title">Approval inbox</h1>
            <p className="page-subtitle">
              Agents pause at sprint planning and sprint review until a human decides.
            </p>
          </div>
        </div>
      </header>
      {projects.error && !projects.data ? (
        <ErrorState error={projects.error} onRetry={projects.reload} />
      ) : !projects.data ? (
        <Loading label="Loading approvals" />
      ) : waiting.length === 0 ? (
        <EmptyState icon={<IconCheck size={22} />} title="You're all caught up">
          No project is waiting for approval. New requests appear here automatically.
        </EmptyState>
      ) : (
        <div className="page-body">
          {waiting.map((p) => (
            <ApprovalCard key={p.id} project={p} onDone={done} showProject />
          ))}
        </div>
      )}
    </div>
  );
}
