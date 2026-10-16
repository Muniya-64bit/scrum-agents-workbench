import type { Backlog, Project, Sprint, SprintDetail, Story, Task } from "../api/types";

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
