// Mirrors the response models in workbench/api/views.py. Keep the two in sync.

export type Phase =
  | "idea"
  | "backlog"
  | "sprint_planning"
  | "execution"
  | "review"
  | "retro"
  | "release"
  | "done";

export type TaskStatus = "todo" | "doing" | "testing" | "done";

export type Role =
  | "product_owner"
  | "scrum_master"
  | "architect"
  | "developer"
  | "qa"
  | "devops";

export interface Project {
  id: number;
  name: string;
  idea: string;
  phase: Phase;
  awaiting_approval: boolean;
}

export interface Story {
  id: number;
  epic_id: number;
  sprint_id: number | null;
  title: string;
  as_a: string;
  i_want: string;
  so_that: string;
  acceptance_criteria: string[];
  priority: number;
  points: number;
  status: string;
}

export interface Epic {
  id: number;
  title: string;
  description: string;
  stories: Story[];
}

export interface Backlog {
  vision: string;
  epics: Epic[];
}

export interface Task {
  id: number;
  story_id: number;
  title: string;
  assignee: string;
  status: TaskStatus;
  updated_at: string;
}

export interface Sprint {
  id: number;
  number: number;
  goal: string;
  capacity: number;
  status: string;
  retro: Record<string, unknown>;
  story_ids: number[];
  points: number;
}

export interface SprintDetail extends Sprint {
  stories: Story[];
  tasks: Task[];
}

/** One entry of the append-only event log (GET /projects/{id}/events and the SSE stream). */
export interface ActivityEvent {
  id: number;
  agent: string;
  kind: string;
  message: string;
  payload: Record<string, unknown>;
  at: string;
}
