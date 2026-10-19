import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { Project, SprintDetail } from "../api/types";
import { phaseLabel, statusLabel } from "../lib/scrum";
import { useResource } from "../lib/useResource";
import { useToast } from "./Toast";
import { IconCheck, IconX } from "./icons";
import { Gherkin } from "./Gherkin";
import { Badge, Button, RoleTag, Spinner } from "./ui";

const GATE_TEXT: Record<string, string> = {
  sprint_planning:
    "The Scrum Master planned this sprint. Approve it to start execution, or reject it to send " +
    "the stories back and have the sprint planned again with your reason.",
  review:
    "The sprint is finished. Approve the increment to move on to the retrospective. If you " +
    "reject it, the retrospective has to respond to your reason.",
};

async function latestSprint(projectId: number): Promise<SprintDetail | null> {
  const sprints = await api.sprints(projectId);
  const last = sprints[sprints.length - 1];
  return last ? api.sprint(last.id) : null;
}

/**
 * What the human is asked to approve at a gate, with Approve and Reject. Reject asks for an
 * optional reason, which is saved on the `rejected` event.
 */
export function ApprovalCard({
  project,
  onDone,
  showProject = false,
}: {
  project: Project;
  onDone: (p: Project) => void;
  showProject?: boolean;
}) {
  const toast = useToast();
  const sprint = useResource(() => latestSprint(project.id), [project.id]);
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const gate = phaseLabel(project.phase);

  async function decide(approved: boolean) {
    setBusy(approved ? "approve" : "reject");
    try {
      const p = await api.approve(project.id, approved, approved ? "" : reason.trim());
      toast("success", `${approved ? "Approved" : "Rejected"} ${gate} for ${project.name}`);
      onDone(p);
    } catch (e) {
      toast("error", e instanceof Error ? e.message : String(e));
      setBusy(null);
    }
  }

  const titleId = `approval-${project.id}`;
  return (
    <section
      className="panel approval"
      aria-labelledby={titleId}
      id={showProject ? undefined : "approval"}
    >
      <header className="approval-header">
        <div>
          <Badge tone="testing">Needs your approval</Badge>
          <h2 id={titleId} className="approval-title">
            {showProject ? (
              <>
                <Link to={`/projects/${project.id}/activity`}>{project.name}</Link>
                <span className="muted"> · {gate}</span>
              </>
            ) : (
              `${gate} is waiting for you`
            )}
          </h2>
          <p className="muted">{GATE_TEXT[project.phase] ?? "Review the agents' work, then decide."}</p>
        </div>
      </header>

      <SprintSummary data={sprint.data} loading={sprint.loading} phase={project.phase} />

      {rejecting ? (
        <div className="approval-reject">
          <label className="field">
            <span className="field-label">Reason (optional)</span>
            <textarea
              className="input textarea"
              rows={2}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. Too much scope for one sprint"
              autoFocus
            />
          </label>
          <div className="approval-actions">
            <Button variant="ghost" onClick={() => setRejecting(false)} disabled={busy !== null}>
              Cancel
            </Button>
            <Button
              variant="danger"
              icon={<IconX />}
              loading={busy === "reject"}
              onClick={() => decide(false)}
            >
              Reject {gate}
            </Button>
          </div>
        </div>
      ) : (
        <div className="approval-actions">
          <Button icon={<IconX />} onClick={() => setRejecting(true)} disabled={busy !== null}>
            Reject…
          </Button>
          <Button
            variant="primary"
            icon={<IconCheck />}
            loading={busy === "approve"}
            disabled={busy !== null}
            onClick={() => decide(true)}
          >
            Approve {gate}
          </Button>
        </div>
      )}
    </section>
  );
}

function SprintSummary({
  data,
  loading,
  phase,
}: {
  data: SprintDetail | null | undefined;
  loading: boolean;
  phase: string;
}) {
  if (loading && data === undefined) {
    return (
      <div className="approval-summary muted">
        <Spinner small /> Loading the sprint…
      </div>
    );
  }
  if (!data) {
    return <p className="approval-summary muted">No sprint has been planned for this project.</p>;
  }
  const done = data.tasks.filter((t) => t.status === "done").length;
  return (
    <div className="approval-summary">
      <p>
        <strong>Sprint {data.number}:</strong> {data.goal || "No goal set"}
      </p>
      <p className="muted">
        {data.stories.length} {data.stories.length === 1 ? "story" : "stories"} · {data.points} of{" "}
        {data.capacity} points · {phase === "review" ? `${done} of ${data.tasks.length} tasks done` : `${data.tasks.length} tasks`}
      </p>
      {data.stories.length > 0 && (
        <>
          <h3 className="approval-subtitle">
            {phase === "review" ? "What was built" : "What you are accepting"}
          </h3>
          <ul className="approval-stories">
            {data.stories.map((s) => {
              const tasks = data.tasks.filter((t) => t.story_id === s.id);
              return (
                <li key={s.id}>
                  <details open className="approval-story">
                    <summary className="approval-story-summary">
                      <span className="story-id">#{s.id}</span>
                      <span className="story-title">{s.title}</span>
                      <Badge tone="neutral">P{s.priority}</Badge>
                      <span className="points">{s.points} pt</span>
                    </summary>
                    <div className="approval-story-body">
                      <p className="user-story">
                        As a <strong>{s.as_a || "user"}</strong>, I want {s.i_want || "…"}
                        {s.so_that && <>, so that {s.so_that}</>}.
                      </p>
                      <h4 className="criteria-title">Acceptance criteria</h4>
                      {s.acceptance_criteria.length === 0 ? (
                        <p className="muted">None written.</p>
                      ) : (
                        <ul className="criteria">
                          {s.acceptance_criteria.map((c, i) => (
                            <li key={i}>
                              <Gherkin text={c} />
                            </li>
                          ))}
                        </ul>
                      )}
                      {tasks.length > 0 && (
                        <>
                          <h4 className="criteria-title">Tasks</h4>
                          <ul className="approval-tasks">
                            {tasks.map((t) => (
                              <li key={t.id}>
                                <span>{t.title}</span>
                                <RoleTag role={t.assignee} />
                                <Badge tone={t.status === "done" ? "done" : "todo"}>
                                  {statusLabel(t.status)}
                                </Badge>
                              </li>
                            ))}
                          </ul>
                        </>
                      )}
                    </div>
                  </details>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </div>
  );
}
