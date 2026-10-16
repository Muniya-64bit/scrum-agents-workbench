import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { backlog, project } from "../test/fixtures";
import { mockApi, renderApp } from "../test/utils";

describe("BacklogPage", () => {
  it("shows the vision, stats, epics and story details", async () => {
    const user = userEvent.setup();
    mockApi({ "GET /projects/1": project, "GET /projects/1/backlog": backlog });
    renderApp("/projects/1/backlog");

    expect(await screen.findByText("Get small things done")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Task management" })).toBeInTheDocument();
    expect(screen.getByText("No stories in this epic yet.")).toBeInTheDocument();
    expect(screen.getByText("Story points").nextSibling).toHaveTextContent("3");

    await user.click(screen.getByText("Create an item"));
    expect(screen.getByText(/to add a to-do/)).toBeVisible();
    expect(screen.getByText("Given")).toHaveClass("gherkin");
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
