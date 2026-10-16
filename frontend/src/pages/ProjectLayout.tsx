import { useState } from "react";
import { Link, Outlet, useOutletContext, useParams } from "react-router-dom";

import { ApiError, api } from "../api/client";
import type { Project } from "../api/types";
import { PhaseBar } from "../components/PhaseBar";
import { useToast } from "../components/Toast";
import { IconArrowRight, IconCheck, IconChevronLeft, IconFolder, IconX } from "../components/icons";
import { Badge, Button, EmptyState, ErrorState, Loading } from "../components/ui";
import { nextPhase, phaseLabel } from "../lib/scrum";
import { useResource } from "../lib/useResource";

export interface ProjectContext {
  project: Project;
  /** Changes after every phase step, so pages know to reload their data. */
  version: number;
}

export function useProject(): ProjectContext {
  return useOutletContext<ProjectContext>();
}

/** Loads the project once for all its pages and shows the header with phase controls. */
export function ProjectLayout() {
  const projectId = Number(useParams().projectId);
  const res = useResource(() => api.getProject(projectId), [projectId]);
  const [version, setVersion] = useState(0);

  if (res.error && !res.data) {
    if (res.error instanceof ApiError && res.error.status === 404) {
      return (
        <EmptyState
          icon={<IconFolder size={22} />}
          title="Project not found"
          action={
            <Link to="/" className="btn btn-secondary">
              <IconChevronLeft /> Back to projects
            </Link>
          }
        >
          There is no project with id {projectId}. It may have been created in another database.
        </EmptyState>
      );
    }
    return <ErrorState error={res.error} onRetry={res.reload} />;
  }
  if (!res.data) return <Loading label="Loading project" />;

  const project = res.data;
  const onChange = (p: Project) => {
    res.setData(() => p);
    setVersion((v) => v + 1);
  };

  return (
    <>
      <header className="page-header">
        <Link to="/" className="back-link">
          <IconChevronLeft size={14} /> All projects
        </Link>
        <div className="page-header-row">
          <div className="page-title-block">
            <h1 className="page-title">{project.name}</h1>
            <p className="page-subtitle">{project.idea}</p>
          </div>
          <PhaseActions project={project} onChange={onChange} />
        </div>
        <PhaseBar phase={project.phase} awaitingApproval={project.awaiting_approval} />
      </header>
      <Outlet context={{ project, version } satisfies ProjectContext} />
    </>
  );
}

function PhaseActions({ project, onChange }: { project: Project; onChange: (p: Project) => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState<"advance" | "approve" | "reject" | null>(null);

  async function run(kind: "advance" | "approve" | "reject") {
    setBusy(kind);
    try {
      const p =
        kind === "advance"
          ? await api.advance(project.id)
          : await api.approve(project.id, kind === "approve");
      onChange(p);
      if (kind !== "advance") toast("success", kind === "approve" ? "Approved" : "Rejected");
    } catch (e) {
      toast("error", e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  if (project.phase === "done") {
    return (
      <div className="phase-actions">
        <Badge tone="done">
          <IconCheck size={12} /> Completed
        </Badge>
      </div>
    );
  }

  if (project.awaiting_approval) {
    return (
      <div className="phase-actions">
        <Badge tone="testing">Awaiting your approval: {phaseLabel(project.phase)}</Badge>
        <Button
          icon={<IconX />}
          loading={busy === "reject"}
          disabled={busy !== null}
          onClick={() => run("reject")}
        >
          Reject
        </Button>
        <Button
          variant="primary"
          icon={<IconCheck />}
          loading={busy === "approve"}
          disabled={busy !== null}
          onClick={() => run("approve")}
        >
          Approve
        </Button>
      </div>
    );
  }

  const next = nextPhase(project.phase);
  return (
    <div className="phase-actions">
      <Button
        variant="primary"
        icon={<IconArrowRight />}
        loading={busy === "advance"}
        onClick={() => run("advance")}
      >
        {busy === "advance"
          ? "Agents working…"
          : next === "done" || !next
            ? "Finish project"
            : `Start ${phaseLabel(next)}`}
      </Button>
    </div>
  );
}
