import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { artifact, burndown, improvementRows, metrics, project, releases } from "../test/fixtures";
import { mockApi, renderApp } from "../test/utils";

function routes(extra: Record<string, unknown> = {}) {
  return {
    "GET /projects/1": project,
    "GET /projects/1/metrics": metrics,
    "GET /sprints/6/burndown": burndown,
    "GET /projects/1/improvement": improvementRows,
    "GET /projects/1/releases": releases,
    ...extra,
  };
}

const card = (n: number) => screen.getByRole("article", { name: `Sprint ${n}` });

describe("Process improvement (PDCA)", () => {
  it("shows one card per sprint with Plan, Do, Check and Act", async () => {
    mockApi(routes());
    renderApp("/projects/1/metrics");
    expect(await screen.findByRole("heading", { name: "Process improvement (PDCA)" })).toBeInTheDocument();
    expect(screen.getByText(/Each sprint is one Plan-Do-Check-Act cycle/)).toBeInTheDocument();
    await screen.findByRole("article", { name: "Sprint 1" });

    const one = card(1);
    for (const block of ["Plan", "Do", "Check", "Act"]) {
      expect(within(one).getByRole("region", { name: block })).toBeInTheDocument();
    }
    expect(within(one).getByText("Capacity 10 · Fix retries 1")).toBeInTheDocument();
    expect(within(one).getByText(/10 pt committed → 7 pt completed/)).toBeInTheDocument();
    // sprint 1 has nothing to compare with
    expect(one.querySelector(".delta")).toBeNull();

    const two = card(2);
    expect(within(two).getByText("Capacity 7 · Fix retries 2 · Test-first")).toBeInTheDocument();
    expect(within(two).getByText(/7 pt committed → 7 pt completed/)).toBeInTheDocument();
  });

  it("marks improvements and regressions with an arrow, a sign and a class", async () => {
    mockApi(routes());
    renderApp("/projects/1/metrics");
    await screen.findByRole("article", { name: "Sprint 2" });
    const check = within(card(2)).getByRole("region", { name: "Check" });
    const row = (label: string) => within(check).getByText(label).closest("div") as HTMLElement;

    const reliability = row("Commitment reliability").querySelector(".delta") as HTMLElement;
    expect(reliability).toHaveTextContent("▲ +30.0 pp");
    expect(reliability).toHaveClass("delta-good");

    const bugs = row("Bugs reported").querySelector(".delta") as HTMLElement;
    expect(bugs).toHaveTextContent("▼ −2");
    expect(bugs).toHaveClass("delta-good"); // fewer bugs is better

    const attempts = row("Fix attempts").querySelector(".delta") as HTMLElement;
    expect(attempts).toHaveTextContent("▲ +1");
    expect(attempts).toHaveClass("delta-bad"); // more fix attempts is worse

    const cost = row("Est. cost").querySelector(".delta") as HTMLElement;
    expect(cost).toHaveTextContent("▲ +$0.0100");
    expect(cost).toHaveClass("delta-bad");
  });

  it("shows what the sprint applied and what the retro proposes as chips", async () => {
    mockApi(routes());
    renderApp("/projects/1/metrics");
    await screen.findByRole("article", { name: "Sprint 2" });

    const applied = within(card(2)).getByRole("list", { name: "Changed after the last retro" });
    expect(within(applied).getByText("capacity 10 → 7")).toBeInTheDocument();
    expect(within(applied).getByText("test-first on")).toBeInTheDocument();

    const proposed = within(card(1)).getByRole("list", { name: "Proposed for the next sprint" });
    expect(within(proposed).getByText("Capacity → 7")).toBeInTheDocument();
    expect(within(proposed).getByText("Test-first on")).toBeInTheDocument();
    expect(within(proposed).getByText("+1 guideline")).toBeInTheDocument();
    expect(within(card(1)).getByText(/Commit to last sprint's velocity/)).toBeInTheDocument();
    expect(within(card(2)).getByText("No process change proposed")).toBeInTheDocument();
  });
});

describe("Releases", () => {
  it("lists the releases and opens the notes in the drawer", async () => {
    const user = userEvent.setup();
    const notes = { ...artifact, id: 9, kind: "release", name: "Release v0.1.0", content: "# Release v0.1.0 notes" };
    mockApi(routes({ "GET /artifacts/9": notes }));
    renderApp("/projects/1/metrics");

    const table = await screen.findByRole("table", { name: "Releases, one per sprint" });
    const row = within(table).getByText("v0.1.0").closest("tr") as HTMLElement;
    expect(within(row).getByText("Sprint 1")).toBeInTheDocument();
    expect(within(row).getByText("2026-10-17")).toBeInTheDocument();
    expect(within(row).getByText("2")).toBeInTheDocument(); // stories
    expect(within(row).getByText("0123456")).toBeInTheDocument(); // sha, 7 characters

    await user.click(within(row).getByRole("button", { name: "v0.1.0" }));
    const dialog = await screen.findByRole("dialog", { name: "Release v0.1.0" });
    await waitFor(() => expect(within(dialog).getByText(/# Release v0\.1\.0 notes/)).toBeInTheDocument());
  });

  it("says so when nothing was released yet", async () => {
    mockApi(routes({ "GET /projects/1/releases": [] }));
    renderApp("/projects/1/metrics");
    expect(await screen.findByText(/No release yet/)).toBeInTheDocument();
  });
});
