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

export function nextPhase(phase: Phase): Phase | null {
  const i = PHASES.findIndex((p) => p.id === phase);
  return i >= 0 && i < PHASES.length - 1 ? PHASES[i + 1].id : null;
}

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
