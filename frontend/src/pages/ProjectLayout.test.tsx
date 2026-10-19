import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { MockEventSource } from "../test/eventSource";
import { processInfo, project } from "../test/fixtures";
import { mockApi, renderApp } from "../test/utils";

const backlogRoute = { "GET /projects/1/backlog": { vision: "", epics: [] } };

describe("phase controls", () => {
  it("advances to the next phase and marks it current", async () => {
    const user = userEvent.setup();
    const calls = mockApi({
      ...backlogRoute,
      "GET /projects/1": { ...project, phase: "idea" },
      "POST /projects/1/advance": { ...project, phase: "backlog" },
    });
    renderApp("/projects/1/backlog");

    await user.click(await screen.findByRole("button", { name: "Start Backlog" }));
    expect(await screen.findByRole("button", { name: "Start Planning" })).toBeInTheDocument();
    expect(screen.getByText("Backlog", { selector: ".phase-current .phase-label" })).toBeInTheDocument();
    expect(calls.filter((c) => c.path === "/projects/1/backlog")).toHaveLength(2); // reloaded
  });

  it("asks for approval at a gate and approves", async () => {
    const user = userEvent.setup();
    const calls = mockApi({
      ...backlogRoute,
      "GET /projects/1": { ...project, phase: "sprint_planning", awaiting_approval: true },
      "POST /projects/1/approve": { ...project, phase: "sprint_planning", awaiting_approval: false },
    });
    renderApp("/projects/1/backlog");

    expect(await screen.findByText(/Awaiting your approval: Planning/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Approve" }));
    expect(await screen.findByRole("button", { name: "Start Execution" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Approved");
    expect(calls.some((c) => c.method === "POST" && c.path === "/projects/1/approve")).toBe(true);
  });

  it("shows the server's reason when a step is refused", async () => {
    const user = userEvent.setup();
    mockApi({
      ...backlogRoute,
      "GET /projects/1": { ...project, phase: "idea" },
      "POST /projects/1/advance": () => ({ status: 409, body: { detail: "Awaiting human approval" } }),
    });
    renderApp("/projects/1/backlog");
    await user.click(await screen.findByRole("button", { name: "Start Backlog" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Awaiting human approval");
  });

  it("shows a completed badge when the project is done", async () => {
    mockApi({ ...backlogRoute, "GET /projects/1": { ...project, phase: "done" } });
    renderApp("/projects/1/backlog");
    expect(await screen.findByText("Completed")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Start/ })).not.toBeInTheDocument();
  });
});

describe("sprint loop", () => {
  it("offers Sprint planning after the release when another sprint follows", async () => {
    mockApi({
      ...backlogRoute,
      "GET /projects/1": { ...project, phase: "release", has_more_sprints: true },
    });
    renderApp("/projects/1/backlog");
    expect(await screen.findByRole("button", { name: "Start Sprint planning" })).toBeInTheDocument();
  });

  it("offers to plan the sprint again after the plan was rejected", async () => {
    mockApi({
      ...backlogRoute,
      "GET /projects/1": { ...project, phase: "sprint_planning", replanning: true },
    });
    renderApp("/projects/1/backlog");
    expect(await screen.findByRole("button", { name: "Plan the sprint again" })).toBeInTheDocument();
  });

  it("finishes the project after the release when no sprint follows", async () => {
    mockApi({ ...backlogRoute, "GET /projects/1": { ...project, phase: "release" } });
    renderApp("/projects/1/backlog");
    expect(await screen.findByRole("button", { name: "Finish project" })).toBeInTheDocument();
  });

  it("shows the sprint number next to the current phase", async () => {
    mockApi({
      ...backlogRoute,
      "GET /projects/1": project,
      "GET /projects/1/process": processInfo,
    });
    renderApp("/projects/1/backlog");
    const sprint = await screen.findByText("Sprint 1", { selector: ".phase-current .phase-sprint" });
    expect(sprint).toBeInTheDocument();
    expect(document.querySelectorAll(".phase-sprint")).toHaveLength(1);
  });

  it("leaves the phase bar alone before any sprint exists", async () => {
    mockApi({
      ...backlogRoute,
      "GET /projects/1": { ...project, phase: "backlog" },
      "GET /projects/1/process": { ...processInfo, current_sprint_number: null },
    });
    renderApp("/projects/1/backlog");
    await screen.findByRole("button", { name: "Start Planning" });
    expect(document.querySelector(".phase-sprint")).toBeNull();
  });
});

describe("live updates", () => {
  it("refreshes the header when a phase event arrives", async () => {
    let phase = "idea";
    mockApi({
      ...backlogRoute,
      "GET /projects/1/events": [],
      "GET /projects/1": () => ({ body: { ...project, phase } }),
    });
    renderApp("/projects/1/backlog");
    expect(await screen.findByRole("button", { name: "Start Backlog" })).toBeInTheDocument();

    phase = "backlog"; // another tab advanced the project
    act(() =>
      MockEventSource.latest().emit({
        id: 9, agent: "orchestrator", kind: "phase_started", message: "backlog", payload: {},
        at: new Date().toISOString(),
      }),
    );
    expect(await screen.findByRole("button", { name: "Start Planning" })).toBeInTheDocument();
  });
});
