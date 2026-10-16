import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api/client";
import type { Project } from "../api/types";
import { IconArrowRight, IconFolder, IconPlus, IconSparkle } from "../components/icons";
import { Badge, Button, EmptyState, ErrorState, Loading } from "../components/ui";
import { phaseLabel } from "../lib/scrum";
import { useResource } from "../lib/useResource";

export function ProjectsPage() {
  const projects = useResource(() => api.listProjects(), []);

  return (
    <div className="page">
      <header className="page-header">
        <div className="page-header-row">
          <div className="page-title-block">
            <h1 className="page-title">Projects</h1>
            <p className="page-subtitle">
              Describe a product idea and the agent team takes it from backlog to release.
            </p>
          </div>
        </div>
      </header>

      <div className="projects-layout">
        <NewProjectForm />
        <section aria-labelledby="your-projects">
          <h2 id="your-projects" className="section-title">
            Your projects
          </h2>
          {projects.error ? (
            <ErrorState error={projects.error} onRetry={projects.reload} />
          ) : !projects.data ? (
            <Loading label="Loading projects" />
          ) : projects.data.length === 0 ? (
            <EmptyState icon={<IconFolder size={22} />} title="No projects yet">
              Create your first project with the form.
            </EmptyState>
          ) : (
            <ul className="project-list">
              {[...projects.data].reverse().map((p) => (
                <ProjectCard key={p.id} project={p} />
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}

function ProjectCard({ project }: { project: Project }) {
  return (
    <li>
      <Link to={`/projects/${project.id}/backlog`} className="project-card">
        <div className="project-card-main">
          <span className="project-card-name">{project.name}</span>
          <span className="project-card-idea">{project.idea}</span>
        </div>
        <div className="project-card-meta">
          {project.awaiting_approval && <Badge tone="testing">Needs approval</Badge>}
          <Badge tone={project.phase === "done" ? "done" : "accent"}>
            {phaseLabel(project.phase)}
          </Badge>
          <IconArrowRight className="project-card-arrow" />
        </div>
      </Link>
    </li>
  );
}

function NewProjectForm() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [idea, setIdea] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const valid = name.trim() !== "" && idea.trim() !== "";

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!valid) return;
    setSaving(true);
    setError("");
    try {
      const p = await api.createProject(name.trim(), idea.trim());
      navigate(`/projects/${p.id}/backlog`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSaving(false);
    }
  }

  return (
    <form className="panel new-project" onSubmit={submit} aria-labelledby="new-project-title">
      <div className="panel-heading">
        <IconSparkle />
        <h2 id="new-project-title">New project</h2>
      </div>
      <label className="field">
        <span className="field-label">Name</span>
        <input
          className="input"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Todo app"
          maxLength={200}
          required
        />
      </label>
      <label className="field">
        <span className="field-label">Product idea</span>
        <textarea
          className="input textarea"
          value={idea}
          onChange={(e) => setIdea(e.target.value)}
          placeholder="A simple to-do app where users can add, complete and delete tasks."
          rows={5}
          required
        />
        <span className="field-hint">
          A sentence or two is enough. The Product Owner agent turns it into a backlog.
        </span>
      </label>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <Button type="submit" variant="primary" icon={<IconPlus />} loading={saving} disabled={!valid}>
        Create project
      </Button>
    </form>
  );
}
