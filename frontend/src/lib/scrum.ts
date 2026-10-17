import type { Phase, Role, TaskStatus } from "../api/types";

export const PHASES: { id: Phase; label: string }[] = [
  { id: "idea", label: "Idea" },
  { id: "backlog", label: "Backlog" },
  { id: "sprint_planning", label: "Planning" },
  { id: "execution", label: "Execution" },
  { id: "review", label: "Review" },
  { id: "retro", label: "Retro" },
  { id: "release", label: "Release" },
  { id: "done", label: "Done" },
];

/** Phases that pause for human approval after their agents run (see orchestrator GATES). */
export const GATES: Phase[] = ["sprint_planning", "review"];

export function phaseLabel(phase: Phase): string {
  return PHASES.find((p) => p.id === phase)?.label ?? phase;
}

/** The phase a step moves to. After the release another sprint may follow (the sprint loop). */
export function nextPhase(phase: Phase, hasMoreSprints = false): Phase | null {
  if (phase === "release" && hasMoreSprints) return "sprint_planning";
  const i = PHASES.findIndex((p) => p.id === phase);
  return i >= 0 && i < PHASES.length - 1 ? PHASES[i + 1].id : null;
}

/** Phases that belong to a sprint, so the phase bar can say which one. */
export const SPRINT_PHASES: Phase[] = ["sprint_planning", "execution", "review", "retro", "release"];

export const STATUSES: { id: TaskStatus; label: string }[] = [
  { id: "todo", label: "To do" },
  { id: "doing", label: "In progress" },
  { id: "testing", label: "Testing" },
  { id: "done", label: "Done" },
];

export function statusLabel(status: string): string {
  return STATUSES.find((s) => s.id === status)?.label ?? status;
}

const ROLE_LABELS: Record<Role | "human", string> = {
  product_owner: "Product Owner",
  scrum_master: "Scrum Master",
  architect: "Architect",
  developer: "Developer",
  qa: "QA",
  devops: "DevOps",
  human: "You",
};

export function roleLabel(role: string): string {
  return ROLE_LABELS[role as Role] ?? (role || "Unassigned");
}
