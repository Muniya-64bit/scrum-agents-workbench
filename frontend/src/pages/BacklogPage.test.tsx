import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { backlog, processInfo, project, story } from "../test/fixtures";
import { mockApi, renderApp } from "../test/utils";

describe("BacklogPage", () => {
  it("shows the vision, stats, epics and story details", async () => {
    mockApi({ "GET /projects/1": project, "GET /projects/1/backlog": backlog });
    renderApp("/projects/1/backlog");

    expect(await screen.findByText("Get small things done")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Task management" })).toBeInTheDocument();
    expect(screen.getByText("No stories in this epic yet.")).toBeInTheDocument();
    expect(screen.getByText("Story points").nextSibling).toHaveTextContent("3");

    // stories are open by default, so the criteria are visible without a click
    expect(screen.getByText(/to add a to-do/)).toBeVisible();
    expect(screen.getByText("Given")).toHaveClass("gherkin");
    expect(screen.getByText("Create an item").closest("summary")).toHaveTextContent("criteri");
  });

  it("collapses and expands every story", async () => {
    const user = userEvent.setup();
    mockApi({ "GET /projects/1": project, "GET /projects/1/backlog": backlog });
    renderApp("/projects/1/backlog");
    await screen.findByText("Create an item");

    await user.click(screen.getByRole("button", { name: "Collapse all stories" }));
    expect(screen.getByText(/to add a to-do/)).not.toBeVisible();
    await user.click(screen.getByRole("button", { name: "Expand all stories" }));
    expect(screen.getByText(/to add a to-do/)).toBeVisible();
  });

  it("marks a finished story as Done and a planned one as In sprint", async () => {
    const finished = { ...story, id: 11, title: "Delete an item", status: "done", sprint_id: 5 };
    const planned = { ...story, id: 12, title: "Edit an item", status: "sprint", sprint_id: 5 };
    mockApi({
      "GET /projects/1": project,
      "GET /projects/1/backlog": {
        ...backlog,
        epics: [{ id: 1, title: "Task management", description: "", stories: [finished, planned] }],
      },
    });
    renderApp("/projects/1/backlog");
    const done = (await screen.findByText("Delete an item")).closest("summary")!;
    expect(done).toHaveTextContent("Done");
    expect(done).not.toHaveTextContent("In sprint");
    expect(screen.getByText("Edit an item").closest("summary")).toHaveTextContent("In sprint");
  });

  it("shows the process levers of the current sprint", async () => {
    mockApi({
      "GET /projects/1": project,
      "GET /projects/1/backlog": backlog,
      "GET /projects/1/process": processInfo,
    });
    renderApp("/projects/1/backlog");
    expect(await screen.findByText("Capacity 10")).toBeInTheDocument();
    expect(screen.getByText("Fix retries 3")).toBeInTheDocument();
    expect(screen.queryByText(/Next sprint/)).toBeNull(); // only at the retro and release
  });

  it("shows the non-functional requirements and the backlog check", async () => {
    mockApi({
      "GET /projects/1": project,
      "GET /projects/1/backlog": {
        ...backlog,
        nfrs: [{ category: "product", requirement: "The API shall be quick.", measure: "p95 < 300 ms" }],
        quality: {
          stories: 1,
          flagged_stories: 1,
          warnings: [
            { rule: "vague_wording", story_id: 10, message: "Wording is vague", detail: "easy" },
            { rule: "nfr_not_measurable", story_id: null, message: "No target", detail: "" },
          ],
        },
      },
    });
    renderApp("/projects/1/backlog");
    expect(await screen.findByText("Non-functional requirements")).toBeInTheDocument();
    expect(screen.getByText("NFR-1")).toBeInTheDocument();
    expect(screen.getByText("Measure: p95 < 300 ms")).toBeInTheDocument();
    expect(screen.getByText("2 warnings")).toBeInTheDocument();
    expect(screen.getByText("Wording is vague")).toBeInTheDocument();
    expect(screen.getByText("NFR")).toBeInTheDocument();
  });

  it("says when the backlog check found nothing", async () => {
    mockApi({
      "GET /projects/1": project,
      "GET /projects/1/backlog": { ...backlog, quality: { stories: 1, flagged_stories: 0, warnings: [] } },
    });
    renderApp("/projects/1/backlog");
    expect(await screen.findByText("No issues")).toBeInTheDocument();
    expect(screen.queryByText("Non-functional requirements")).toBeNull();
  });

  it("tells the user how to get a backlog when it is empty", async () => {
    mockApi({
      "GET /projects/1": { ...project, phase: "idea" },
      "GET /projects/1/backlog": { vision: "", epics: [] },
    });
    renderApp("/projects/1/backlog");
    expect(await screen.findByText("No backlog yet")).toBeInTheDocument();
    expect(screen.getByText(/Start the Backlog phase/)).toBeInTheDocument();
  });

  it("shows a not-found state for an unknown project", async () => {
    mockApi({});
    renderApp("/projects/42/backlog");
    expect(await screen.findByText("Project not found")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Back to projects/ })).toHaveAttribute("href", "/");
  });
});
