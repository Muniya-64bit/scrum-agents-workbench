import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { MockEventSource } from "../test/eventSource";
import { processInfo, project, sprint, sprintDetail } from "../test/fixtures";
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
      "GET /projects/1/sprints": [sprint],
      "GET /sprints/5": sprintDetail,
      "POST /projects/1/approve": { ...project, phase: "sprint_planning", awaiting_approval: false },
    });
    renderApp("/projects/1/backlog");

    expect(await screen.findByText(/Awaiting your approval: Planning/)).toBeInTheDocument();
    // the header does not approve blindly; the card on the page shows what is accepted
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    const card = await screen.findByRole("region", { name: "Planning is waiting for you" });
    expect(await within(card).findByText("What you are accepting")).toBeInTheDocument();
    expect(within(card).getByText("Acceptance criteria")).toBeInTheDocument();
    await user.click(within(card).getByRole("button", { name: "Approve Planning" }));
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

describe("maintenance", () => {
  it("offers a problem report only on a finished project", async () => {
    mockApi({ ...backlogRoute, "GET /projects/1": { ...project, phase: "execution" } });
    renderApp("/projects/1/backlog");
    await screen.findByText("Todo app");
    expect(screen.queryByText("Found a problem after the release?")).not.toBeInTheDocument();
  });

  it("sends the report and offers the maintenance sprint", async () => {
    const user = userEvent.setup();
    const calls = mockApi({
      ...backlogRoute,
      "GET /projects/1": { ...project, phase: "done" },
      "POST /projects/1/maintenance": { ...project, phase: "release", has_more_sprints: true },
    });
    renderApp("/projects/1/backlog");

    await user.click(await screen.findByText("Found a problem after the release?"));
    await user.type(screen.getByLabelText("Problem"), "Empty title is accepted");
    await user.type(screen.getByLabelText("What happens"), "It returns 201 instead of 422.");
    await user.selectOptions(screen.getByLabelText("Size (points)"), "3");
    await user.click(screen.getByRole("button", { name: "Request a fix" }));

    expect(await screen.findByRole("button", { name: "Start Sprint planning" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("The fix is in the backlog");
    const post = calls.find((c) => c.method === "POST" && c.path === "/projects/1/maintenance");
    expect(post?.body).toEqual({
      title: "Empty title is accepted",
      description: "It returns 201 instead of 422.",
      points: 3,
    });
    expect(screen.queryByText("Found a problem after the release?")).not.toBeInTheDocument();
  });

  it("shows the server's reason when the report is refused", async () => {
    const user = userEvent.setup();
    mockApi({
      ...backlogRoute,
      "GET /projects/1": { ...project, phase: "done" },
      "POST /projects/1/maintenance": () => ({ status: 409, body: { detail: "Only a finished project takes a maintenance request" } }),
    });
    renderApp("/projects/1/backlog");
    await user.click(await screen.findByText("Found a problem after the release?"));
    await user.type(screen.getByLabelText("Problem"), "A bug");
    await user.type(screen.getByLabelText("What happens"), "It breaks");
    await user.click(screen.getByRole("button", { name: "Request a fix" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Only a finished project");
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
