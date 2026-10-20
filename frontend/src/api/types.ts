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
  /** True at `release` when another sprint follows (see the orchestrator's sprint loop). */
  has_more_sprints: boolean;
  /** True after the human rejected the sprint plan: the next step plans the same sprint again. */
  replanning?: boolean;
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

/** A non-functional requirement with a measurable target. */
export interface Nfr {
  category: string;
  requirement: string;
  measure: string;
}

export interface QualityWarning {
  rule: string;
  /** null for a warning about a non-functional requirement */
  story_id: number | null;
  message: string;
  detail: string;
}

/** The latest rule-based backlog check (the `backlog_validated` event). */
export interface BacklogQuality {
  stories: number;
  flagged_stories: number;
  warnings: QualityWarning[];
}

export interface Backlog {
  vision: string;
  epics: Epic[];
  nfrs?: Nfr[];
  quality?: BacklogQuality | null;
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
  release: TraceItem[];
  other: TraceItem[];
  sprint_number: number | null;
  /** Every sprint the story was planned into, carried-over ones included. */
  sprints: number[];
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

/** The levers a retrospective proposes (`Sprint.retro.process_changes`); null/absent keeps a lever. */
export interface ProposedChanges {
  capacity?: number | null;
  max_fix_retries?: number | null;
  test_first?: boolean | null;
  add_guidelines?: string[];
  reason?: string;
}

/** Measured results of a sprint, as compared in the PDCA view. */
export interface ImprovementCheck {
  commitment_reliability: number | null;
  first_pass_yield: number | null;
  test_pass_rate: number | null;
  bugs_reported: number;
  fix_attempts: number;
  est_cost_usd: number;
}

/** One Plan-Do-Check-Act cycle (one sprint): `GET /projects/{id}/improvement`. */
export interface ImprovementRow {
  sprint_number: number;
  plan: { process: Partial<ProcessConfig>; changes_applied: ProcessDiff; reason: string };
  do: { committed_points: number; completed_points: number };
  check: ImprovementCheck;
  /** Change since the previous sprint; null for sprint 1 or when a value is missing. */
  deltas: { [K in keyof ImprovementCheck]: number | null };
  act: {
    went_well: string[];
    went_wrong: string[];
    actions: string[];
    proposed_changes: ProposedChanges;
  };
}

/** Changed levers only, as [old, new] pairs. */
export type ProcessDiff = Record<string, [unknown, unknown]>;

/** One sprint release: `GET /projects/{id}/releases`. */
export interface Release {
  artifact_id: number;
  version: string;
  sprint_id: number;
  sprint_number: number | null;
  created_at: string;
  story_ids: number[];
  sha: string;
}

/** One check made when a sprint was released: the app starts, serves its contract, a requirement
 *  is met, the security scan. */
export interface ReleaseCheck {
  version: string;
  sprint_id: number | null;
  name: string;
  status: "passed" | "failed" | "skipped" | "met" | "not met" | "unverified";
  detail: string;
}

/** The process levers (docs/agents.md, "Retrospective and process levers"). */
export interface ProcessConfig {
  capacity: number;
  max_fix_retries: number;
  test_first: boolean;
  guidelines: string[];
}

/** `GET /projects/{id}/process`: the sprint's levers and what the retro changes for the next. */
export interface ProcessInfo {
  current: ProcessConfig;
  current_sprint_number: number | null;
  next: ProcessConfig;
  /** Changed levers only, as [old, new] pairs. */
  next_changes: ProcessDiff;
  next_reason: string;
}
