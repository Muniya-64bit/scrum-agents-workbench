import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { project } from "../test/fixtures";
import { mockApi, renderApp } from "../test/utils";

describe("ProjectsPage", () => {
  it("lists projects with their phase", async () => {
    mockApi({ "GET /projects": [project] });
    renderApp("/");
    const card = await screen.findByRole("link", { name: /Todo app/ });
    expect(within(card).getByText("Execution")).toBeInTheDocument();
  });

  it("shows an empty state when there are no projects", async () => {
    mockApi({ "GET /projects": [] });
    renderApp("/");
    expect(await screen.findByText("No projects yet")).toBeInTheDocument();
  });

  it("creates a project and opens its backlog", async () => {
    const user = userEvent.setup();
    const calls = mockApi({
      "GET /projects": [],
      "POST /projects": { ...project, id: 7, name: "Notes", phase: "idea" },
      "GET /projects/7": { ...project, id: 7, name: "Notes", phase: "idea" },
      "GET /projects/7/backlog": { vision: "", epics: [] },
    });
    renderApp("/");
    const button = screen.getByRole("button", { name: "Create project" });
    expect(button).toBeDisabled();

    await user.type(screen.getByLabelText("Name"), "Notes");
    await user.type(screen.getByLabelText(/Product idea/), "A notes app");
    expect(button).toBeEnabled();
    await user.click(button);

    expect(await screen.findByRole("heading", { name: "Notes" })).toBeInTheDocument();
    expect(await screen.findByText("No backlog yet")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ name: "Notes", idea: "A notes app" });
  });

  it("shows the API error if creating fails", async () => {
    const user = userEvent.setup();
    mockApi({ "GET /projects": [], "POST /projects": () => ({ status: 500, body: { detail: "db locked" } }) });
    renderApp("/");
    await user.type(screen.getByLabelText("Name"), "x");
    await user.type(screen.getByLabelText(/Product idea/), "y");
    await user.click(screen.getByRole("button", { name: "Create project" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("db locked");
  });
});
