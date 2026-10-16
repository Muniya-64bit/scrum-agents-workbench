import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";

import { App } from "../App";
import { ToastProvider } from "../components/Toast";

import { artifact, project, traceRows } from "../test/fixtures";
import { mockApi, renderApp } from "../test/utils";

const routes = () => ({
  "GET /projects/1": project,
  "GET /projects/1/traceability": traceRows,
  "GET /artifacts/2": artifact,
});

const table = () => screen.getByRole("table", { name: /Traceability from user story/ });
const rowOf = (title: string) => within(table()).getByText(title).closest("tr") as HTMLElement;

describe("TraceabilityPage", () => {
  it("shows one row per story with artifact chips and results", async () => {
    mockApi(routes());
    renderApp("/projects/1/traceability");
    await screen.findByText("A: sign in");

    const a = rowOf("A: sign in");
    expect(within(a).getByRole("button", { name: /DES\s*A design/ })).toBeInTheDocument();
    expect(within(a).getByRole("button", { name: /CODE\s*app\/a\.py/ })).toBeInTheDocument();
    expect(within(a).getByRole("button", { name: /TEST\s*tests\/test_a\.py/ })).toBeInTheDocument();
    expect(within(a).getByText("2 passed")).toBeInTheDocument();
    expect(within(a).getByText("2/2")).toBeInTheDocument();

    const b = rowOf("B: sign out");
    expect(within(b).getByText("1 passed")).toBeInTheDocument();
    expect(within(b).getByText("1 failed")).toBeInTheDocument();
    expect(within(b).getByText("1 open bug")).toBeInTheDocument();
    expect(within(b).getByText("0/1")).toBeInTheDocument();

    expect(within(rowOf("E: extra")).getByText("Not run")).toBeInTheDocument();
  });

  it("summarises completeness, failing tests, open bugs and AC coverage", async () => {
    mockApi(routes());
    renderApp("/projects/1/traceability");
    await screen.findByText("A: sign in");
    const stat = (label: string) => screen.getByText(label).nextElementSibling;
    expect(stat("Trace completeness")).toHaveTextContent("50.0%"); // A of the two planned rows
    expect(stat("Stories with failing tests")).toHaveTextContent("1");
    expect(stat("Open bugs")).toHaveTextContent("1");
    expect(stat("AC coverage")).toHaveTextContent("50.0%"); // (2 + 0 + 0) of 4 criteria
  });

  it("marks planned stories with gaps and names what is missing", async () => {
    mockApi(routes());
    renderApp("/projects/1/traceability");
    await screen.findByText("A: sign in");
    const header = within(rowOf("B: sign out")).getByRole("rowheader");
    expect(header).toHaveAccessibleDescription("Missing: design, test");
    expect(within(rowOf("A: sign in")).queryByTitle(/Missing/)).toBeNull();
    // Stories outside a sprint are not flagged
    expect(within(rowOf("E: extra")).queryByTitle(/Missing/)).toBeNull();
  });

  it("filters to gaps only and keeps the choice in the URL", async () => {
    const user = userEvent.setup();
    mockApi(routes());
    renderApp("/projects/1/traceability");
    await screen.findByText("A: sign in");
    await user.click(screen.getByRole("checkbox", { name: "Gaps only" }));
    expect(screen.queryByText("A: sign in")).toBeNull();
    expect(screen.queryByText("E: extra")).toBeNull();
    expect(screen.getByText("B: sign out")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Gaps only" })).toBeChecked();
  });

  it("reads the sprint filter from the URL", async () => {
    mockApi(routes());
    renderApp("/projects/1/traceability?sprint=2");
    await screen.findByText("B: sign out");
    expect(screen.queryByText("A: sign in")).toBeNull();
    expect(screen.getByRole("combobox", { name: "Sprint" })).toHaveValue("2");
  });

  it("filters stories that are not planned", async () => {
    const user = userEvent.setup();
    mockApi(routes());
    renderApp("/projects/1/traceability");
    await screen.findByText("A: sign in");
    await user.selectOptions(screen.getByRole("combobox", { name: "Sprint" }), "none");
    expect(screen.getByText("E: extra")).toBeInTheDocument();
    expect(screen.queryByText("A: sign in")).toBeNull();
  });

  it("says when no story matches", async () => {
    mockApi(routes());
    renderApp("/projects/1/traceability?status=done");
    expect(await screen.findByText("No stories match these filters.")).toBeInTheDocument();
  });

  it("opens an artifact in the drawer", async () => {
    const user = userEvent.setup();
    mockApi(routes());
    renderApp("/projects/1/traceability");
    await screen.findByText("A: sign in");
    await user.click(within(rowOf("A: sign in")).getByRole("button", { name: /CODE/ }));
    const dialog = await screen.findByRole("dialog", { name: "app/a.py" });
    await waitFor(() => expect(within(dialog).getByText(/x = 1/)).toBeInTheDocument());
    expect(within(dialog).getByText("Linked stories: #10")).toBeInTheDocument();
  });

  it("shows an empty state without stories", async () => {
    mockApi({ ...routes(), "GET /projects/1/traceability": [] });
    renderApp("/projects/1/traceability");
    expect(await screen.findByText("No stories yet")).toBeInTheDocument();
  });

  it("links to the page from the sidebar", async () => {
    mockApi(routes());
    renderApp("/projects/1/traceability");
    expect(await screen.findByRole("link", { name: "Traceability" })).toHaveAttribute(
      "href",
      "/projects/1/traceability",
    );
  });

  it("writes the filters to the URL", async () => {
    const user = userEvent.setup();
    mockApi(routes());
    function Probe() {
      const loc = useLocation();
      return <output aria-label="url">{loc.pathname + loc.search}</output>;
    }
    render(
      <MemoryRouter initialEntries={["/projects/1/traceability"]}>
        <ToastProvider>
          <App />
          <Probe />
        </ToastProvider>
      </MemoryRouter>,
    );
    await screen.findByText("A: sign in");
    await user.click(screen.getByRole("checkbox", { name: "Gaps only" }));
    expect(screen.getByLabelText("url")).toHaveTextContent("/projects/1/traceability?gaps=1");
    await user.click(screen.getByRole("checkbox", { name: "Gaps only" }));
    expect(screen.getByLabelText("url")).toHaveTextContent(/^\/projects\/1\/traceability$/);
  });
});
