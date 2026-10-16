import type {
  Artifact,
  Backlog,
  Burndown,
  ProcessInfo,
  Project,
  ProjectMetrics,
  Release,
  Sprint,
  SprintDetail,
  SprintMetrics,
  Story,
  Task,
  TraceRow,
} from "../api/types";

export const project: Project = {
  id: 1,
  name: "Todo app",
  idea: "A simple to-do app",
  phase: "execution",
  awaiting_approval: false,
};

export const story: Story = {
  id: 10,
  epic_id: 1,
  sprint_id: 5,
  title: "Create an item",
  as_a: "user",
  i_want: "to add a to-do",
  so_that: "I remember it",
  acceptance_criteria: ["Given the app When I add a title Then it is listed"],
  priority: 1,
  points: 3,
  status: "sprint",
};

export const backlog: Backlog = {
  vision: "Get small things done",
  epics: [
    { id: 1, title: "Task management", description: "Core features", stories: [story] },
    { id: 2, title: "Organisation", description: "", stories: [] },
  ],
};

export const tasks: Task[] = [
  { id: 100, story_id: 10, title: "Build POST /items", assignee: "developer", status: "todo", updated_at: "" },
  { id: 101, story_id: 10, title: "Test create item", assignee: "qa", status: "testing", updated_at: "" },
];

export const sprint: Sprint = {
  id: 5,
  number: 1,
  goal: "Users can add items",
  capacity: 10,
  status: "active",
  retro: {},
  story_ids: [10],
  points: 3,
};

export const sprintDetail: SprintDetail = { ...sprint, stories: [story], tasks };

const sprintOneMetrics: SprintMetrics = {
  sprint_id: 5,
  sprint_number: 1,
  goal: "Users can add items",
  closed: true,
  committed_points: 8,
  committed_stories: 3,
  completed_points: 5,
  completed_stories: 2,
  commitment_reliability: 0.625,
  carried_over_stories: 1,
  test_runs: 4,
  first_pass_yield: 0.333,
  test_pass_rate: 0.8,
  bugs_reported: 2,
  bugs_fixed_in_sprint: 1,
  bugs_open_at_end: 1,
  fix_attempts: 2,
  retry_limit_hits: 1,
  llm_calls: 3,
  input_tokens: 10000,
  output_tokens: 2000,
  cache_hits: 1,
  llm_invalid_outputs: 1,
  est_cost_usd: 0.04,
  cost_per_completed_point: 0.008,
  trace_completeness: 0.333,
  ac_coverage: 0.4,
  duration_s: 125,
  process: { capacity: 8, max_fix_retries: 1, test_first: false, guidelines: [] },
};

const sprintTwoMetrics: SprintMetrics = {
  ...sprintOneMetrics,
  sprint_id: 6,
  sprint_number: 2,
  goal: "Finish the carried story",
  committed_points: 5,
  committed_stories: 2,
  completed_points: 5,
  completed_stories: 2,
  commitment_reliability: 1,
  carried_over_stories: 0,
  test_runs: 2,
  first_pass_yield: 1,
  test_pass_rate: 1,
  bugs_reported: 0,
  bugs_open_at_end: 0,
  fix_attempts: 1,
  retry_limit_hits: 0,
  llm_calls: 2,
  input_tokens: 5000,
  output_tokens: 1000,
  cache_hits: 0,
  llm_invalid_outputs: 0,
  est_cost_usd: 0.02,
  cost_per_completed_point: 0.004,
  trace_completeness: 0,
  ac_coverage: 0,
  duration_s: 45,
  process: { capacity: 5, max_fix_retries: 2, test_first: false, guidelines: [] },
};

export const metrics: ProjectMetrics = {
  project: {
    stories_total: 4,
    stories_done: 4,
    points_total: 10,
    points_done: 10,
    sprint_count: 2,
    avg_velocity: 5,
    total_llm_calls: 6,
    total_input_tokens: 16000,
    total_output_tokens: 3500,
    total_cost_usd: 0.067,
    llm_modes: ["live"],
    loc: 2,
    trace_completeness: 0.25,
  },
  sprints: [sprintOneMetrics, sprintTwoMetrics],
  unattributed: { llm_calls: 1, input_tokens: 1000, output_tokens: 500, est_cost_usd: 0.007 },
  gqm: [
    {
      id: "G1",
      goal: "Improve the predictability of sprint delivery",
      viewpoint: "Scrum Master",
      questions: [
        {
          id: "Q1",
          text: "How much of what we commit do we deliver?",
          metrics: [
            {
              key: "commitment_reliability",
              name: "Commitment reliability",
              unit: "ratio",
              definition: "Completed points divided by committed points.",
            },
          ],
        },
      ],
    },
  ],
  pricing: {
    model: "claude-sonnet-5-5",
    input_per_mtok: 2,
    output_per_mtok: 10,
    source: "Claude Sonnet 5.5 list price",
  },
};

export const burndown: Burndown = {
  sprint_id: 6,
  sprint_number: 2,
  committed_points: 5,
  remaining_points: 0,
  duration_s: 45,
  closed: true,
  series: [
    { t: 0, step: 0, at: "2026-10-17T10:00:00", remaining: 5, story_id: null, label: "Sprint start" },
    { t: 20, step: 1, at: "2026-10-17T10:00:20", remaining: 2, story_id: 12, label: "Done: C: reset password" },
    { t: 40, step: 2, at: "2026-10-17T10:00:40", remaining: 0, story_id: 13, label: "Done: D: profile" },
    { t: 45, step: 3, at: "2026-10-17T10:00:45", remaining: 0, story_id: null, label: "Sprint end" },
  ],
  ideal: [
    { t: 0, remaining: 5 },
    { t: 45, remaining: 0 },
  ],
};

export const traceRows: TraceRow[] = [
  {
    story_id: 10,
    title: "A: sign in",
    status: "sprint",
    design: [{ artifact_id: 1, name: "A design", kind: "design", path: "", version: 1 }],
    code: [{ artifact_id: 2, name: "app/a.py", kind: "code", path: "app/a.py", version: 1 }],
    test: [{ artifact_id: 3, name: "tests/test_a.py", kind: "test", path: "tests/test_a.py", version: 1 }],
    release: [
      { artifact_id: 9, name: "Release v0.1.0", kind: "release", path: "releases/v0.1.0.md", version: 1 },
    ],
    other: [],
    sprint_number: 1,
    tests_passed: 2,
    tests_failed: 0,
    last_test_ok: true,
    open_bugs: 0,
    ac_count: 2,
    test_count: 2,
    complete: true,
  },
  {
    story_id: 11,
    title: "B: sign out",
    status: "sprint",
    design: [],
    code: [{ artifact_id: 4, name: "app/b.py", kind: "code", path: "app/b.py", version: 1 }],
    test: [],
    release: [],
    other: [],
    sprint_number: 2,
    tests_passed: 1,
    tests_failed: 1,
    last_test_ok: false,
    open_bugs: 1,
    ac_count: 1,
    test_count: 0,
    complete: false,
  },
  {
    story_id: 12,
    title: "E: extra",
    status: "backlog",
    design: [],
    code: [],
    test: [],
    release: [],
    other: [],
    sprint_number: null,
    tests_passed: 0,
    tests_failed: 0,
    last_test_ok: null,
    open_bugs: 0,
    ac_count: 1,
    test_count: 0,
    complete: false,
  },
];

export const artifact: Artifact = {
  id: 2,
  kind: "code",
  name: "app/a.py",
  path: "app/a.py",
  version: 1,
  created_by: "developer",
  created_at: "2026-10-17T10:00:00",
  content: "x = 1\ny = 2\n",
  story_ids: [10],
};

export const releases: Release[] = [
  {
    artifact_id: 9,
    version: "v0.1.0",
    sprint_id: 6,
    sprint_number: 1,
    created_at: "2026-10-17T10:00:00",
    story_ids: [10, 11],
    sha: "0123456789abcdef0123456789abcdef01234567",
  },
];

export const processInfo: ProcessInfo = {
  current: { capacity: 10, max_fix_retries: 3, test_first: false, guidelines: [] },
  current_sprint_number: 1,
  next: {
    capacity: 7,
    max_fix_retries: 3,
    test_first: true,
    guidelines: ["Write the acceptance tests first"],
  },
  next_changes: { capacity: [10, 7], test_first: [false, true] },
  next_reason: "Commit to last sprint's velocity",
};
