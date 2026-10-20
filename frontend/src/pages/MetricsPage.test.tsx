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

function rowOf(table: HTMLElement, name: string): HTMLElement {
  return within(table).getByRole("rowheader", { name: new RegExp(name) }).closest("tr")!;
}

describe("MetricsPage", () => {
  it("opens with the outcome: what the project delivered", async () => {
    mockApi(routes());
    renderApp("/projects/1/metrics");
    await screen.findByRole("heading", { name: "Results" });

    const outcome = screen.getByRole("region", { name: "Project outcome" });
    expect(within(outcome).getByText("Complete")).toBeInTheDocument();
    expect(within(outcome).getByText("All 10 points delivered after 2 sprints.")).toBeInTheDocument();
    expect(within(outcome).getByText("4 of 4")).toBeInTheDocument(); // stories done
    expect(within(outcome).getByText("Live run (live) with claude-sonnet-5-5.")).toBeInTheDocument();
  });

  it("says plainly when nothing was delivered", async () => {
    const none = { ...metrics.project, stories_done: 0, points_done: 0, points_total: 31 };
    mockApi(routes({ "GET /projects/1/metrics": { ...metrics, project: none } }));
    renderApp("/projects/1/metrics");
    const outcome = await screen.findByRole("region", { name: "Project outcome" });
    expect(within(outcome).getByText("Nothing delivered")).toBeInTheDocument();
    expect(
      within(outcome).getByText("No story is done: 0 of 31 points delivered after 2 sprints."),
    ).toBeInTheDocument();
  });

  it("shows what every sprint planned and completed, not only the first", async () => {
    mockApi(routes());
    renderApp("/projects/1/metrics");
    const table = await screen.findByRole("table", { name: "Planned and completed work for every sprint" });

    const one = rowOf(table, "Sprint 1");
    expect(within(one).getByText(/3 stories · 8 pt/)).toBeInTheDocument(); // planned
    expect(within(one).getByText(/2 stories · 5 pt/)).toBeInTheDocument(); // completed
    expect(within(one).getByText("62.5%")).toBeInTheDocument();
    const two = rowOf(table, "Sprint 2");
    expect(within(two).getAllByText(/2 stories · 5 pt/)).toHaveLength(2);
    expect(within(two).getByText("100.0%")).toBeInTheDocument();
    expect(screen.getByText("Users can add items")).toBeInTheDocument(); // the goal of sprint 1
  });

  it("says what each sprint did, and why it did not finish what it planned", async () => {
    mockApi(routes());
    renderApp("/projects/1/metrics");
    const table = await screen.findByRole("table", { name: "Planned and completed work for every sprint" });
    // Sprint 1 planned 3 stories and completed 2; sprint 2 completed everything it planned
    expect(
      within(table).getByText(/4 test runs, 80.0% passed · 2 bugs found · 2 fix attempts, 1 fixed/),
    ).toBeInTheDocument();
    expect(within(table).getByText(/some tests still failed; 1 bug is still open/)).toBeInTheDocument();
    expect(within(table).getAllByText("Not completed because:")).toHaveLength(1);
    expect(within(table).getAllByText("What happened:")).toHaveLength(2);
  });

  it("keeps the charts to a sensible size and describes them", async () => {
    mockApi(routes());
    renderApp("/projects/1/metrics");
    const chart = await screen.findByRole("img", { name: /Committed and completed/ });
    expect(chart.closest(".results-chart")).not.toBeNull();
    expect(within(chart).getByText("Sprint 1")).toBeInTheDocument();
    expect(within(chart).getByText("Sprint 2")).toBeInTheDocument();
  });

  it("shows the key measures of the latest sprint with their meaning and change", async () => {
    mockApi(routes());
    renderApp("/projects/1/metrics");
    await screen.findByRole("heading", { name: "Sprint detail" });

    const reliability = tile("Commitment reliability");
    expect(within(reliability).getByText("100.0%")).toBeInTheDocument();
    expect(within(reliability).getByText("▲ +37.5 pp")).toHaveClass("delta-good");
    expect(
      within(reliability).getByText("Completed points divided by committed points."),
    ).toBeInTheDocument();

    expect(within(tile("Velocity")).getByText("5 pt")).toBeInTheDocument();
    expect(within(tile("Velocity")).getByText("±0")).toHaveClass("delta-flat");
    expect(within(tile("Open bugs")).getByText(/−1/)).toHaveClass("delta-good");
  });

  it("switches the sprint in focus and loads its burndown", async () => {
    const user = userEvent.setup();
    const calls = mockApi(routes());
    renderApp("/projects/1/metrics");

    expect(await screen.findByRole("img", { name: /Burndown, sprint 2/ })).toBeInTheDocument();
    const sprint2 = screen.getByRole("button", { name: "Sprint 2" });
    expect(sprint2).toHaveAttribute("aria-pressed", "true");

    await user.click(screen.getByRole("button", { name: "Sprint 1" }));
    await waitFor(() => expect(calls.map((c) => c.path)).toContain("/sprints/5/burndown"));
    expect(await screen.findByRole("img", { name: /Burndown, sprint 1/ })).toBeInTheDocument();
    expect(screen.getByText(/Sprint 1 goal:/)).toBeInTheDocument();
    expect(within(tile("Velocity")).getByText("5 pt")).toBeInTheDocument();
    expect(within(tile("Velocity")).getByText("of 8 pt planned")).toBeInTheDocument();
  });

  it("shows quality with the columns that matter and the rest on request", async () => {
    const user = userEvent.setup();
    mockApi(routes());
    renderApp("/projects/1/metrics");
    const quality = await screen.findByRole("table", { name: "Quality metrics per sprint" });
    expect(within(quality).getByText("80.0%")).toBeInTheDocument();
    expect(within(quality).queryByRole("columnheader", { name: "Fix attempts" })).toBeNull();

    await user.click(screen.getByRole("button", { name: "Show all columns" }));
    expect(within(quality).getByRole("columnheader", { name: "Fix attempts" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show fewer columns" })).toHaveAttribute("aria-expanded", "true");
  });

  it("explains each quality column from its GQM definition", async () => {
    mockApi(routes({ "GET /projects/1/metrics": { ...metrics, gqm: [{
      ...metrics.gqm[0],
      questions: [{ ...metrics.gqm[0].questions[0], metrics: [
        { key: "test_pass_rate", name: "Test pass rate", unit: "ratio", definition: "Passed tests divided by all tests." },
      ] }],
    }] } }));
    renderApp("/projects/1/metrics");
    const header = await screen.findByRole("columnheader", { name: "Pass rate" });
    expect(header).toHaveAttribute("title", "Passed tests divided by all tests.");
    expect(screen.getByText("What do these columns mean?")).toBeInTheDocument();
  });

  it("totals the cost first and keeps the per-sprint table behind a toggle", async () => {
    mockApi(routes());
    renderApp("/projects/1/metrics");
    const cost = await screen.findByRole("group", { name: "Cost totals" });
    expect(within(cost).getByText("$0.0670")).toBeInTheDocument();
    expect(within(cost).getByText("≈ $0.0067 per point")).toBeInTheDocument();
    expect(within(cost).getByText("19,500")).toBeInTheDocument(); // 16,000 in + 3,500 out

    const table = screen.getByRole("table", { name: /estimated cost per sprint/, hidden: true });
    expect(within(table).getByRole("rowheader", { name: /Backlog & design/, hidden: true })).toBeInTheDocument();
    expect(within(table).getByRole("rowheader", { name: "Total", hidden: true })).toBeInTheDocument();
    expect(within(table).getByText("10,000")).toBeInTheDocument();
  });

  it("says a local model has no per-token price", async () => {
    const free = { ...metrics.pricing, input_per_mtok: 0, output_per_mtok: 0 };
    mockApi(routes({ "GET /projects/1/metrics": { ...metrics, pricing: free } }));
    renderApp("/projects/1/metrics");
    expect(await screen.findByText("local model, no per-token price")).toBeInTheDocument();
    expect(
      screen.getByText("claude-sonnet-5-5 runs locally and has no per-token price, so its cost is shown as $0."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/list price/)).toBeNull();
  });

  it("explains how the metrics were chosen", async () => {
    mockApi(routes());
    renderApp("/projects/1/metrics");
    expect(await screen.findByText("Show goals, questions and metrics")).toBeInTheDocument();
    expect(screen.getByText("G1")).toBeInTheDocument();
    expect(screen.getAllByText(/Goal-Question-Metric/).length).toBeGreaterThan(0);
  });

  it("offers jump links to every section", async () => {
    mockApi(routes());
    renderApp("/projects/1/metrics");
    const nav = await screen.findByRole("navigation", { name: "On this page" });
    const ids = within(nav).getAllByRole("link").map((a) => a.getAttribute("href")?.slice(1));
    expect(ids).toEqual(["sprints", "detail", "quality", "cost", "releases", "improvement", "method"]);
    for (const id of ids) expect(document.getElementById(id as string)).not.toBeNull();
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
    expect(
      await screen.findByText("Mock run: no model was called, so no tokens were spent."),
    ).toBeInTheDocument();
  });

  it("shows an empty state before the first sprint", async () => {
    mockApi(
      routes({
        "GET /projects/1/metrics": { ...metrics, sprints: [], project: { ...metrics.project, sprint_count: 0 } },
      }),
    );
    renderApp("/projects/1/metrics");
    expect(await screen.findByText("No sprint data yet")).toBeInTheDocument();
    expect(screen.getByText("Results appear after sprint planning.")).toBeInTheDocument();
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
    await screen.findByRole("heading", { name: "Sprint detail" });
    expect(within(tile("First-pass yield")).getByText("—")).toBeInTheDocument();
  });

  it("links to the page from the sidebar", async () => {
    mockApi(routes());
    renderApp("/projects/1/metrics");
    const link = await screen.findByRole("link", { name: "Results" });
    expect(link).toHaveAttribute("href", "/projects/1/metrics");
  });
});
