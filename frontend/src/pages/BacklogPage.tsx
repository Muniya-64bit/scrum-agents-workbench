import type { ReactNode } from "react";

import { api } from "../api/client";
import type { Story } from "../api/types";
import { IconList } from "../components/icons";
import { ProcessChips } from "../components/ProcessChips";
import { Badge, EmptyState, ErrorState, Loading, type Tone } from "../components/ui";
import { useResource } from "../lib/useResource";
import { useProject } from "./ProjectLayout";

export function BacklogPage() {
  const { project, version, process } = useProject();
  const backlog = useResource(() => api.backlog(project.id), [project.id, version]);

  if (backlog.error) return <ErrorState error={backlog.error} onRetry={backlog.reload} />;
  if (!backlog.data) return <Loading label="Loading backlog" />;

  const { vision, epics } = backlog.data;
  const stories = epics.flatMap((e) => e.stories);
  if (stories.length === 0 && epics.length === 0) {
    return (
      <EmptyState icon={<IconList size={22} />} title="No backlog yet">
        {project.phase === "idea"
          ? "Start the Backlog phase and the Product Owner agent will write epics and user stories."
          : "The Product Owner agent has not added any stories to this project."}
      </EmptyState>
    );
  }

  const points = stories.reduce((sum, s) => sum + s.points, 0);
  const planned = stories.filter((s) => s.sprint_id !== null).length;

  return (
    <div className="page-body">
      <ProcessChips info={process} phase={project.phase} />
      {vision && (
        <section className="vision" aria-label="Product vision">
          <span className="eyebrow">Product vision</span>
          <p>{vision}</p>
        </section>
      )}

      <dl className="stats">
        <Stat label="Epics" value={epics.length} />
        <Stat label="Stories" value={stories.length} />
        <Stat label="Story points" value={points} />
        <Stat label="In a sprint" value={`${planned} / ${stories.length}`} />
      </dl>

      {epics.map((epic) => (
        <section key={epic.id} className="panel epic" aria-labelledby={`epic-${epic.id}`}>
          <header className="epic-header">
            <div>
              <h2 id={`epic-${epic.id}`} className="epic-title">
                {epic.title}
              </h2>
              {epic.description && <p className="epic-description">{epic.description}</p>}
            </div>
            <span className="epic-count">
              {epic.stories.length} {epic.stories.length === 1 ? "story" : "stories"}
            </span>
          </header>
          {epic.stories.length === 0 ? (
            <p className="muted epic-empty">No stories in this epic yet.</p>
          ) : (
            <ul className="story-list">
              {epic.stories.map((s) => (
                <StoryRow key={s.id} story={s} />
              ))}
            </ul>
          )}
        </section>
      ))}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="stat">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

const PRIORITY_TONE: Record<number, Tone> = { 1: "danger", 2: "testing", 3: "accent" };

function StoryRow({ story }: { story: Story }) {
  return (
    <li className="story">
      <details>
        <summary className="story-summary">
          <span className="story-id">#{story.id}</span>
          <span className="story-title">{story.title}</span>
          <span className="story-meta">
            <Badge tone={PRIORITY_TONE[story.priority] ?? "neutral"}>P{story.priority}</Badge>
            {story.status === "done" ? (
              <Badge tone="done">Done</Badge>
            ) : (
              story.sprint_id !== null && <Badge tone="doing">In sprint</Badge>
            )}
            <span className="points" title="Story points">
              {story.points} pt
            </span>
          </span>
        </summary>
        <div className="story-body">
          {(story.as_a || story.i_want) && (
            <p className="user-story">
              As a <strong>{story.as_a || "user"}</strong>, I want {story.i_want || "…"}
              {story.so_that && <>, so that {story.so_that}</>}.
            </p>
          )}
          <h3 className="criteria-title">Acceptance criteria</h3>
          {story.acceptance_criteria.length === 0 ? (
            <p className="muted">None written yet.</p>
          ) : (
            <ul className="criteria">
              {story.acceptance_criteria.map((c, i) => (
                <li key={i}>
                  <Gherkin text={c} />
                </li>
              ))}
            </ul>
          )}
        </div>
      </details>
    </li>
  );
}

/** Bold the Given / When / Then / And keywords so criteria are easy to scan. */
function Gherkin({ text }: { text: string }) {
  const parts = text.split(/\b(Given|When|Then|And)\b/);
  return (
    <>
      {parts.map((part, i) =>
        /^(Given|When|Then|And)$/.test(part) ? (
          <strong key={i} className="gherkin">
            {part}
          </strong>
        ) : (
          part
        ),
      )}
    </>
  );
}
