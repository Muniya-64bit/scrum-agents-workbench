import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { backlog, processInfo, project, sprintDetail, sprint, tasks } from "../test/fixtures";
import { mockApi, renderApp } from "../test/utils";

const column = (name: string) => screen.getByRole("region", { name });

describe("BoardPage", () => {
  it("puts each task in its status column with story and role", async () => {
    mockApi({
      "GET /projects/1": project,
      "GET /projects/1/sprints": [sprint],
      "GET /sprints/5": sprintDetail,
    });
    renderApp("/projects/1/board");

    expect(await screen.findByText("Users can add items")).toBeInTheDocument();
    const todo = column("To do");
    expect(within(todo).getByText("Build POST /items")).toBeInTheDocument();
    expect(within(todo).getByText("#10 Create an item")).toBeInTheDocument();
    expect(within(todo).getByText("Developer")).toBeInTheDocument();
    expect(within(column("Testing")).getByText("Test create item")).toBeInTheDocument();
    expect(within(column("Done")).getByText("Drop tasks here")).toBeInTheDocument();
    expect(screen.getByText("0 / 2 tasks done")).toBeInTheDocument();
  });

  it("shows the sprint's process and the change planned for the next sprint", async () => {
    mockApi({
      "GET /projects/1": { ...project, phase: "retro" },
      "GET /projects/1/sprints": [sprint],
      "GET /sprints/5": sprintDetail,
      "GET /projects/1/process": processInfo,
    });
    renderApp("/projects/1/board");
    const bar = await screen.findByRole("region", { name: "Sprint process" });
    expect(within(bar).getByText("Capacity 10")).toBeInTheDocument();
    expect(within(bar).getByText("Next sprint: capacity 10 → 7, test-first on")).toBeInTheDocument();
  });

  it("moves a task with the status menu and saves it", async () => {
    const user = userEvent.setup();
    const calls = mockApi({
      "GET /projects/1": project,
      "GET /projects/1/sprints": [sprint],
      "GET /sprints/5": sprintDetail,
      "PATCH /tasks/100": { ...tasks[0], status: "done" },
    });
    renderApp("/projects/1/board");

    await user.selectOptions(await screen.findByLabelText('Status of "Build POST /items"'), "done");
    expect(within(column("Done")).getByText("Build POST /items")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PATCH")).toEqual({
      method: "PATCH",
      path: "/tasks/100",
      body: { status: "done" },
    });
    expect(screen.getByText("1 / 2 tasks done")).toBeInTheDocument();
  });

  it("moves the card back and explains when saving fails", async () => {
    const user = userEvent.setup();
    mockApi({
      "GET /projects/1": project,
      "GET /projects/1/sprints": [sprint],
      "GET /sprints/5": sprintDetail,
      "PATCH /tasks/100": () => ({ status: 500, body: { detail: "database is locked" } }),
    });
    renderApp("/projects/1/board");

    await user.selectOptions(await screen.findByLabelText('Status of "Build POST /items"'), "doing");
    expect(await screen.findByRole("alert")).toHaveTextContent("database is locked");
    expect(within(column("To do")).getByText("Build POST /items")).toBeInTheDocument();
  });

  it("shows all project tasks when no sprint exists yet", async () => {
    mockApi({
      "GET /projects/1": project,
      "GET /projects/1/sprints": [],
      "GET /projects/1/tasks": tasks,
      "GET /projects/1/backlog": backlog,
    });
    renderApp("/projects/1/board");
    expect(await screen.findByText("No sprint planned yet")).toBeInTheDocument();
    expect(within(column("To do")).getByText("Build POST /items")).toBeInTheDocument();
  });

  it("shows an empty state without tasks", async () => {
    mockApi({
      "GET /projects/1": { ...project, phase: "backlog" },
      "GET /projects/1/sprints": [],
      "GET /projects/1/tasks": [],
      "GET /projects/1/backlog": { vision: "", epics: [] },
    });
    renderApp("/projects/1/board");
    expect(await screen.findByText("No tasks yet")).toBeInTheDocument();
    expect(screen.getByText(/Advance the project to Planning/)).toBeInTheDocument();
  });
});
