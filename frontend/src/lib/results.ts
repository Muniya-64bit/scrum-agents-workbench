// Pure logic behind the Results page: what happened in the project, in plain words.
// Components only render what these functions return, so the rules are unit tested here.

import type { GqmGoal, Pricing, ProjectMetrics, SprintMetrics } from "../api/types";
import { pct } from "./format";

export type VerdictTone = "good" | "warn" | "bad";

export interface Verdict {
  tone: VerdictTone;
  label: string;
  text: string;
}

export interface Outcome {
  verdict: Verdict;
  pointsDone: number;
  pointsTotal: number;
  storiesDone: number;
  storiesTotal: number;
  sprintCount: number;
  /** Pass rate of the latest sprint that ran tests; null when no sprint did. */
  testPassRate: number | null;
  /** Bugs still open at the end of the latest sprint. */
  openBugs: number;
  linesOfCode: number;
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** What the project delivered, judged on the points of its stories (not on sprint commitments,
 *  which count a carried-over story once per sprint). */
export function summarizeOutcome(data: ProjectMetrics): Outcome {
  const { project, sprints } = data;
  const withTests = [...sprints].reverse().find((s) => s.test_runs > 0);
  return {
    verdict: verdictFor(project.points_done, project.points_total, sprints.length),
    pointsDone: project.points_done,
    pointsTotal: project.points_total,
    storiesDone: project.stories_done,
    storiesTotal: project.stories_total,
    sprintCount: sprints.length,
    testPassRate: withTests ? withTests.test_pass_rate : null,
    openBugs: sprints.length > 0 ? sprints[sprints.length - 1].bugs_open_at_end : 0,
    linesOfCode: project.loc,
  };
}

export function verdictFor(done: number, total: number, sprintCount: number): Verdict {
  const after = `after ${plural(sprintCount, "sprint", "sprints")}`;
  if (total === 0) {
    return { tone: "warn", label: "No stories", text: "The backlog has no stories yet." };
  }
  if (done === 0) {
    return {
      tone: "bad",
      label: "Nothing delivered",
      text: `No story is done: 0 of ${total} points delivered ${after}.`,
    };
  }
  if (done < total) {
    return {
      tone: "warn",
      label: "In progress",
      text: `${done} of ${total} points delivered (${pct(done / total)}) ${after}.`,
    };
  }
  return { tone: "good", label: "Complete", text: `All ${total} points delivered ${after}.` };
}

/** The sprint to show first: the latest one that is closed, else the last one. */
export function defaultSprint(sprints: SprintMetrics[]): SprintMetrics {
  const closed = sprints.filter((s) => s.closed);
  return closed.length > 0 ? closed[closed.length - 1] : sprints[sprints.length - 1];
}

/** The sprint before `sprint` in the list, for "change since" figures. */
export function previousSprint(sprints: SprintMetrics[], sprint: SprintMetrics): SprintMetrics | undefined {
  const index = sprints.findIndex((s) => s.sprint_id === sprint.sprint_id);
  return index > 0 ? sprints[index - 1] : undefined;
}

export interface MeterRow {
  sprint: SprintMetrics;
  /** Bar widths in percent of the largest commitment, so sprints compare at a glance. */
  plannedWidth: number;
  completedWidth: number;
}

export function meterRows(sprints: SprintMetrics[]): MeterRow[] {
  const max = Math.max(1, ...sprints.map((s) => s.committed_points));
  return sprints.map((sprint) => ({
    sprint,
    plannedWidth: (sprint.committed_points / max) * 100,
    completedWidth: (sprint.completed_points / max) * 100,
  }));
}

/** The GQM definition of a metric, so tiles and table headers can say what they measure. */
export function definitionOf(gqm: GqmGoal[], key: string): string {
  for (const goal of gqm) {
    for (const question of goal.questions) {
      const found = question.metrics.find((m) => m.key === key);
      if (found) return found.definition;
    }
  }
  return "";
}

/** True when the model costs nothing per token, e.g. a local one. */
export function isFree(pricing: Pricing): boolean {
  return pricing.input_per_mtok === 0 && pricing.output_per_mtok === 0;
}

export function modeLine(data: ProjectMetrics): string {
  const modes = data.project.llm_modes;
  if (modes.length === 0 || (modes.length === 1 && modes[0] === "mock")) {
    return "Mock run: no model was called, so no tokens were spent.";
  }
  return `Live run (${modes.join(", ")}) with ${data.pricing.model}.`;
}
