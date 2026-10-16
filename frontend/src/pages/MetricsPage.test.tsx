import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { Burndown } from "../api/types";
import { burndown, metrics, project } from "../test/fixtures";
import { mockApi, renderApp } from "../test/utils";

const sprintOneBurndown: Burndown = {
  ...burndown,
  sprint_id: 5,
  sprint_number: 1,
  committed_points: 8,
  remaining_points: 3,
  series: [
    { ...burndown.series[0], remaining: 8 },
    { ...burndown.series[3], remaining: 3 },
  ],
  ideal: [
    { t: 0, remaining: 8 },
    { t: 45, remaining: 0 },
  ],
};

function tile(label: string): HTMLElement {
  const found = Array.from(document.querySelectorAll<HTMLElement>(".kpi")).find(
    (el) => el.querySelector(".kpi-label")?.textContent === label,
  );
  if (!found) throw new Error(`No KPI tile "${label}"`);
  return found;
}

function routes(extra: Record<string, unknown> = {}) {
  return {
    "GET /projects/1": project,
    "GET /projects/1/metrics": metrics,
    "GET /sprints/6/burndown": burndown,
    "GET /sprints/5/burndown": sprintOneBurndown,
    ...extra,
  };
}

describe("MetricsPage", () => {
  it("shows the KPI tiles for the latest sprint with changes against the previous one", async () => {
    mockApi(routes());
    renderApp("/projects/1/metrics");
    await screen.findByRole("heading", { name: "Metrics" });

    const reliability = tile("Commitment reliability");
    expect(within(reliability).getByText("100.0%")).toBeInTheDocument();
    const change = within(reliability).getByText("▲ +37.5 pp");
    expect(change).toHaveClass("delta-good");

    expect(within(tile("Velocity")).getByText("5 pt")).toBeInTheDocument();
    expect(within(tile("Velocity")).getByText("±0")).toHaveClass("delta-flat");
    expect(within(tile("Open bugs")).getByText(/−1/)).toHaveClass("delta-good");
    expect(within(tile("Est. cost")).getByText("$0.0670")).toBeInTheDocument();
    expect(within(tile("Est. cost")).getByText("≈ $0.0067 per point")).toBeInTheDocument();
  });

  it("draws the burndown of the latest sprint and loads another when the sprint changes", async () => {
    const user = userEvent.setup();
    const calls = mockApi(routes());
    renderApp("/projects/1/metrics");

    expect(await screen.findByRole("img", { name: /Sprint 2/ })).toBeInTheDocument();
    await user.selectOptions(screen.getByRole("combobox", { name: "Sprint" }), "Sprint 1");
    await waitFor(() =>
      expect(calls.map((c) => c.path)).toContain("/sprints/5/burndown"),
    );
    expect(await screen.findByRole("img", { name: /Burndown, sprint 1/ })).toBeInTheDocument();
  });

  it("shows velocity, quality, cost and GQM sections", async () => {
    mockApi(routes());
    renderApp("/projects/1/metrics");
    const velocity = await screen.findByRole("img", { name: /Committed and completed/ });
    expect(within(velocity).getByText("Sprint 1")).toBeInTheDocument();
    expect(within(velocity).getByText("Sprint 2")).toBeInTheDocument();

    const quality = screen.getByRole("table", { name: "Quality metrics per sprint" });
    expect(within(quality).getByText("80.0%")).toBeInTheDocument();

    const cost = screen.getByRole("table", { name: /estimated cost per sprint/ });
    expect(within(cost).getByRole("rowheader", { name: /Backlog & design/ })).toBeInTheDocument();
    expect(within(cost).getByRole("rowheader", { name: "Total" })).toBeInTheDocument();
    expect(within(cost).getAllByText("$0.0670")).toHaveLength(1);
    expect(within(cost).getByText("10,000")).toBeInTheDocument();

    expect(screen.getByText(/How these metrics were chosen/)).toBeInTheDocument();
    expect(screen.getByText("G1")).toBeInTheDocument();
    expect(screen.getAllByText(/Goal-Question-Metric/).length).toBeGreaterThan(0);
  });

  it("tells whether tokens were spent", async () => {
    mockApi(
      routes({
        "GET /projects/1/metrics": {
          ...metrics,
          project: { ...metrics.project, llm_modes: ["mock"] },
        },
      }),
    );
    renderApp("/projects/1/metrics");
    expect(await screen.findByText("Mode: mock — no tokens were spent")).toBeInTheDocument();
  });

  it("names the live mode", async () => {
    mockApi(routes());
    renderApp("/projects/1/metrics");
    expect(await screen.findByText("Mode: live")).toBeInTheDocument();
  });

  it("shows an empty state before the first sprint", async () => {
    mockApi(
      routes({
        "GET /projects/1/metrics": { ...metrics, sprints: [], project: { ...metrics.project, sprint_count: 0 } },
      }),
    );
    renderApp("/projects/1/metrics");
    expect(await screen.findByText("No sprint data yet")).toBeInTheDocument();
    expect(screen.getByText("Metrics appear after sprint planning.")).toBeInTheDocument();
  });

  it("shows dashes for undefined ratios", async () => {
    const first = { ...metrics.sprints[0], commitment_reliability: null, first_pass_yield: null };
    mockApi(
      routes({
        "GET /projects/1/metrics": { ...metrics, sprints: [first] },
        "GET /sprints/5/burndown": sprintOneBurndown,
      }),
    );
    renderApp("/projects/1/metrics");
    await screen.findByRole("heading", { name: "Metrics" });
    expect(within(tile("First-pass yield")).getByText("—")).toBeInTheDocument();
  });

  it("links to the page from the sidebar", async () => {
    mockApi(routes());
    renderApp("/projects/1/metrics");
    const link = await screen.findByRole("link", { name: "Metrics" });
    expect(link).toHaveAttribute("href", "/projects/1/metrics");
  });
});
