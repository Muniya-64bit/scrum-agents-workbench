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

export interface BurndownPoint {
  t: number;
  step: number;
  at: string;
  remaining: number;
  story_id: number | null;
  label: string;
}

export interface IdealPoint {
  t: number;
  remaining: number;
}

export interface Burndown {
  sprint_id: number;
  sprint_number: number;
  committed_points: number;
  remaining_points: number;
  duration_s: number;
  closed: boolean;
  series: BurndownPoint[];
  ideal: IdealPoint[];
}

/** Per-sprint GQM metrics. Ratios and cost per point are null when undefined (see docs/metrics.md). */
export interface SprintMetrics {
  sprint_id: number;
  sprint_number: number;
  goal: string;
  closed: boolean;
  committed_points: number;
  committed_stories: number;
  completed_points: number;
  completed_stories: number;
  commitment_reliability: number | null;
  carried_over_stories: number;
  test_runs: number;
  first_pass_yield: number | null;
  test_pass_rate: number | null;
  bugs_reported: number;
  bugs_fixed_in_sprint: number;
  bugs_open_at_end: number;
  fix_attempts: number;
  retry_limit_hits: number;
  llm_calls: number;
  input_tokens: number;
  output_tokens: number;
  cache_hits: number;
  llm_invalid_outputs: number;
  est_cost_usd: number;
  cost_per_completed_point: number | null;
  trace_completeness: number | null;
  ac_coverage: number | null;
  duration_s: number;
  process: Record<string, unknown>;
}

export interface ProjectTotals {
  stories_total: number;
  stories_done: number;
  points_total: number;
  points_done: number;
  sprint_count: number;
  avg_velocity: number | null;
  total_llm_calls: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_usd: number;
  llm_modes: string[];
  loc: number;
  trace_completeness: number | null;
}

export interface Usage {
  llm_calls: number;
  input_tokens: number;
  output_tokens: number;
  est_cost_usd: number;
}

export interface GqmMetric {
  key: string;
  name: string;
  definition: string;
  unit: string;
}

export interface GqmQuestion {
  id: string;
  text: string;
  metrics: GqmMetric[];
}

export interface GqmGoal {
  id: string;
  goal: string;
  viewpoint: string;
  questions: GqmQuestion[];
}

export interface Pricing {
  model: string;
  input_per_mtok: number;
  output_per_mtok: number;
  source: string;
}

export interface ProjectMetrics {
  project: ProjectTotals;
  sprints: SprintMetrics[];
  unattributed: Usage;
  gqm: GqmGoal[];
  pricing: Pricing;
}

export interface TraceItem {
  artifact_id: number;
  name: string;
  kind: string;
  path: string;
  version: number;
}

/** One row of the story -> design -> code -> test matrix. */
export interface TraceRow {
  story_id: number;
  title: string;
  status: string;
  design: TraceItem[];
  code: TraceItem[];
  test: TraceItem[];
  other: TraceItem[];
  sprint_number: number | null;
  tests_passed: number;
  tests_failed: number;
  last_test_ok: boolean | null;
  open_bugs: number;
  ac_count: number;
  test_count: number;
  complete: boolean;
}

export interface ArtifactSummary {
  id: number;
  kind: string;
  name: string;
  path: string;
  version: number;
  created_by: string;
  created_at: string;
}

export interface Artifact extends ArtifactSummary {
  content: string;
  story_ids: number[];
}
