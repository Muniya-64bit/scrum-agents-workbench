import { metrics } from "../test/fixtures";
import {
  defaultSprint,
  definitionOf,
  isFree,
  meterRows,
  modeLine,
  previousSprint,
  summarizeOutcome,
  verdictFor,
} from "./results";

describe("verdictFor", () => {
  it.each([
    [0, 0, 1, "warn", "No stories"],
    [0, 31, 3, "bad", "Nothing delivered"],
    [5, 10, 2, "warn", "In progress"],
    [10, 10, 1, "good", "Complete"],
  ])("%i of %i points after %i sprints is %s", (done, total, sprints, tone, label) => {
    expect(verdictFor(done, total, sprints)).toMatchObject({ tone, label });
  });

  it("says how much was delivered and after how many sprints", () => {
    expect(verdictFor(0, 31, 3).text).toBe("No story is done: 0 of 31 points delivered after 3 sprints.");
    expect(verdictFor(5, 10, 1).text).toBe("5 of 10 points delivered (50.0%) after 1 sprint.");
  });
});

describe("summarizeOutcome", () => {
  it("reads the project totals and the latest sprint", () => {
    const o = summarizeOutcome(metrics);
    expect(o).toMatchObject({
      pointsDone: 10,
      pointsTotal: 10,
      storiesDone: 4,
      sprintCount: 2,
      openBugs: 0,
      linesOfCode: 2,
      testPassRate: 1,
    });
    expect(o.verdict.label).toBe("Complete");
  });

  it("takes the pass rate of the latest sprint that ran tests", () => {
    const [first, second] = metrics.sprints;
    const noTests = { ...second, test_runs: 0, test_pass_rate: null };
    expect(summarizeOutcome({ ...metrics, sprints: [first, noTests] }).testPassRate).toBe(0.8);
    expect(summarizeOutcome({ ...metrics, sprints: [{ ...first, test_runs: 0 }] }).testPassRate).toBeNull();
  });
});

describe("sprint helpers", () => {
  const [first, second] = metrics.sprints;

  it("shows the latest closed sprint first, else the last one", () => {
    expect(defaultSprint([{ ...first, closed: true }, { ...second, closed: false }])).toMatchObject({
      sprint_number: 1,
    });
    expect(defaultSprint([{ ...first, closed: false }, { ...second, closed: false }])).toMatchObject({
      sprint_number: 2,
    });
  });

  it("finds the previous sprint", () => {
    expect(previousSprint(metrics.sprints, second)).toBe(first);
    expect(previousSprint(metrics.sprints, first)).toBeUndefined();
  });

  it("scales the planned and completed bars to the biggest commitment", () => {
    const rows = meterRows(metrics.sprints); // committed 8 and 5, completed 5 and 5
    expect(rows.map((r) => [r.plannedWidth, r.completedWidth])).toEqual([
      [100, 62.5],
      [62.5, 62.5],
    ]);
    expect(meterRows([{ ...first, committed_points: 0, completed_points: 0 }])[0].plannedWidth).toBe(0);
  });
});

describe("labels", () => {
  it("looks up the definition of a metric", () => {
    expect(definitionOf(metrics.gqm, "commitment_reliability")).toBe(
      "Completed points divided by committed points.",
    );
    expect(definitionOf(metrics.gqm, "nope")).toBe("");
  });

  it("knows a free model and describes the run", () => {
    expect(isFree({ ...metrics.pricing, input_per_mtok: 0, output_per_mtok: 0 })).toBe(true);
    expect(isFree(metrics.pricing)).toBe(false);
    expect(modeLine(metrics)).toBe("Live run (live) with claude-sonnet-5-5.");
    expect(modeLine({ ...metrics, project: { ...metrics.project, llm_modes: ["mock"] } })).toBe(
      "Mock run: no model was called, so no tokens were spent.",
    );
  });
});
