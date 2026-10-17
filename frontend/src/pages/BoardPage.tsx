import { useState, type DragEvent } from "react";

import { api } from "../api/client";
import type { Sprint, SprintDetail, Story, Task, TaskStatus } from "../api/types";
import { ProcessChips } from "../components/ProcessChips";
import { useToast } from "../components/Toast";
import { IconBoard } from "../components/icons";
import { EmptyState, ErrorState, Loading, RoleTag, Spinner } from "../components/ui";
import { STATUSES, statusLabel } from "../lib/scrum";
import { useResource } from "../lib/useResource";
import { useProject } from "./ProjectLayout";

interface BoardData {
  sprints: Sprint[];
  sprint: SprintDetail | undefined;
  tasks: Task[];
  stories: Map<number, Story>;
}

/** The chosen sprint (latest by default); without sprints, every task in the project. */
async function loadBoard(projectId: number, sprintId: number | null): Promise<BoardData> {
  const sprints = await api.sprints(projectId);
  const chosen = sprints.find((s) => s.id === sprintId) ?? sprints[sprints.length - 1];
  if (chosen) {
    const sprint = await api.sprint(chosen.id);
    return { sprints, sprint, tasks: sprint.tasks, stories: byId(sprint.stories) };
  }
  const [tasks, backlog] = await Promise.all([api.tasks(projectId), api.backlog(projectId)]);
  return {
    sprints,
    sprint: undefined,
    tasks,
    stories: byId(backlog.epics.flatMap((e) => e.stories)),
  };
}

function byId(stories: Story[]): Map<number, Story> {
  return new Map(stories.map((s) => [s.id, s]));
}

export function BoardPage() {
  const { project, version, process } = useProject();
  const toast = useToast();
  const [sprintId, setSprintId] = useState<number | null>(null);
  const board = useResource(() => loadBoard(project.id, sprintId), [project.id, sprintId, version]);
  const [pending, setPending] = useState<Set<number>>(new Set());

  if (board.error) return <ErrorState error={board.error} onRetry={board.reload} />;
  if (!board.data) return <Loading label="Loading board" />;
  const { sprints, sprint, tasks, stories } = board.data;

  async function move(task: Task, status: TaskStatus) {
    if (task.status === status) return;
    const setStatus = (s: TaskStatus) =>
      board.setData((d) => d && { ...d, tasks: d.tasks.map((t) => (t.id === task.id ? { ...t, status: s } : t)) });
    setStatus(status); // optimistic: the card moves at once
    setPending((p) => new Set(p).add(task.id));
    try {
      await api.updateTask(task.id, status);
    } catch (e) {
      setStatus(task.status);
      toast("error", `Could not move "${task.title}": ${e instanceof Error ? e.message : e}`);
    } finally {
      setPending((p) => {
        const next = new Set(p);
        next.delete(task.id);
        return next;
      });
    }
  }

  const done = tasks.filter((t) => t.status === "done").length;
  const pct = tasks.length ? Math.round((done / tasks.length) * 100) : 0;

  return (
    <div className="page-body">
      <ProcessChips info={process} phase={project.phase} />
      <section className="board-summary" aria-label="Sprint summary">
        <div className="board-summary-main">
          {sprints.length > 1 ? (
            <label className="sprint-select">
              <span className="sr-only">Sprint</span>
              <select
                className="input select"
                value={sprint?.id}
                onChange={(e) => setSprintId(Number(e.target.value))}
              >
                {sprints.map((s) => (
                  <option key={s.id} value={s.id}>
                    Sprint {s.number}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <span className="eyebrow">{sprint ? `Sprint ${sprint.number}` : "All tasks"}</span>
          )}
          <h2 className="board-goal">
            {sprint ? sprint.goal || "No sprint goal set" : "No sprint planned yet"}
          </h2>
        </div>
        {tasks.length > 0 && (
          <div className="board-progress">
            {sprint && (
              <span className="muted">
                {sprint.points} of {sprint.capacity} points
              </span>
            )}
            <span className="muted">
              {done} / {tasks.length} tasks done
            </span>
            <div
              className="progress"
              role="progressbar"
              aria-label="Tasks done"
              aria-valuenow={pct}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <span style={{ width: `${pct}%` }} />
            </div>
          </div>
        )}
      </section>

      {tasks.length === 0 ? (
        <EmptyState icon={<IconBoard size={22} />} title="No tasks yet">
          {sprint
            ? "This sprint has no tasks."
            : project.phase === "idea" || project.phase === "backlog"
              ? "Tasks appear here once the Scrum Master plans a sprint. Advance the project to Planning."
              : "The Scrum Master has not planned any tasks for this project."}
        </EmptyState>
      ) : (
        <div className="board">
          {STATUSES.map((col) => (
            <Column
              key={col.id}
              status={col.id}
              tasks={tasks.filter((t) => t.status === col.id)}
              stories={stories}
              pending={pending}
              onMove={move}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function Column({
  status,
  tasks,
  stories,
  pending,
  onMove,
}: {
  status: TaskStatus;
  tasks: Task[];
  stories: Map<number, Story>;
  pending: Set<number>;
  onMove: (task: Task, status: TaskStatus) => void;
}) {
  const [over, setOver] = useState(false);

  function drop(e: DragEvent) {
    e.preventDefault();
    setOver(false);
    const raw = e.dataTransfer.getData("application/x-task");
    if (!raw) return;
    onMove(JSON.parse(raw) as Task, status);
  }

  return (
    <section
      className={`column column-${status} ${over ? "column-over" : ""}`}
      aria-labelledby={`col-${status}`}
      onDragOver={(e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        setOver(true);
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node)) setOver(false);
      }}
      onDrop={drop}
    >
      <header className="column-header">
        <span className="column-dot" />
        <h3 id={`col-${status}`}>{statusLabel(status)}</h3>
        <span className="column-count">{tasks.length}</span>
      </header>
      <ul className="column-cards">
        {tasks.map((t) => (
          <TaskCard
            key={t.id}
            task={t}
            story={stories.get(t.story_id)}
            pending={pending.has(t.id)}
            onMove={onMove}
          />
        ))}
        {tasks.length === 0 && <li className="column-empty">Drop tasks here</li>}
      </ul>
    </section>
  );
}

function TaskCard({
  task,
  story,
  pending,
  onMove,
}: {
  task: Task;
  story: Story | undefined;
  pending: boolean;
  onMove: (task: Task, status: TaskStatus) => void;
}) {
  const [dragging, setDragging] = useState(false);
  return (
    <li
      className={`card ${dragging ? "card-dragging" : ""}`}
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData("application/x-task", JSON.stringify(task));
        e.dataTransfer.effectAllowed = "move";
        setDragging(true);
      }}
      onDragEnd={() => setDragging(false)}
    >
      {story && (
        <span className="card-story" title={story.title}>
          #{story.id} {story.title}
        </span>
      )}
      <span className="card-title">{task.title}</span>
      <div className="card-footer">
        <RoleTag role={task.assignee} />
        {pending && <Spinner small label="Saving" />}
        <select
          className="card-status"
          value={task.status}
          onChange={(e) => onMove(task, e.target.value as TaskStatus)}
          aria-label={`Status of "${task.title}"`}
        >
          {STATUSES.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
        </select>
      </div>
    </li>
  );
}
