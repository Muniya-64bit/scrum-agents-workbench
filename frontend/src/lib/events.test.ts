import type { ActivityEvent } from "../api/types";
import { actorInitials, describeEvent, parseTime, timeAgo } from "./events";

const ev = (kind: string, message = "", payload = {}): ActivityEvent => ({
  id: 1,
  agent: "developer",
  kind,
  message,
  payload,
  at: "2026-10-16T10:00:00",
});

describe("describeEvent", () => {
  it.each([
    [ev("phase_started", "sprint_planning"), "Started the Planning phase", "accent"],
    [ev("approval_requested", "review"), "Waiting for your approval of Review", "testing"],
    [ev("rejected", "Too big", { phase: "sprint_planning" }), "Rejected Planning: Too big", "danger"],
    [ev("approved", "", { phase: "review" }), "Approved Review", "done"],
    [ev("story_created", "Add item"), "Added story “Add item”", "neutral"],
    [ev("task_updated", "Build API -> done"), "Moved “Build API” to Done", "done"],
    [ev("artifact_created", "app.py", { artifact_kind: "api_spec" }), "Wrote api spec “app.py”", "neutral"],
    [ev("bug_reported", "500 on save"), "Reported a bug: 500 on save", "danger"],
    [ev("file_rejected", "/tests/x.py"), "Rejected a file with an unsafe or disallowed path: /tests/x.py", "danger"],
    [ev("tests_missing", "No valid tests for story #12"), "No valid tests for story #12: QA wrote no usable test file", "danger"],
    [ev("docker_build_failed", "permission denied\nsecond line"), "The Docker image could not be built: permission denied", "danger"],
    [ev("agent_message", "Please fix bug #4", { to: "developer" }), "Told the Developer: Please fix bug #4", "accent"],
    [ev("tests_revised", "Story #3: Add"), "QA rewrote its tests after a mistake in the test code: Story #3: Add", "accent"],
    [ev("code_committed", "Story #3: Add"), "Code committed: Story #3: Add", "neutral"],
    [ev("nfrs_set", "2 non-functional requirement(s)"), "Wrote 2 non-functional requirement(s)", "neutral"],
    [
      ev("backlog_validated", "1 warning(s) on 1 of 2 stories", { warnings: [{ rule: "x" }] }),
      "Checked the backlog: 1 warning(s) on 1 of 2 stories",
      "testing",
    ],
    [ev("backlog_validated", "0 warning(s)", { warnings: [] }), "Checked the backlog: 0 warning(s)", "done"],
    [
      ev("entry_criteria_checked", "0 of 1 entry criteria met", { phase: "sprint_planning", unmet: ["x"] }),
      "Entry criteria of Planning: 0 of 1 entry criteria met",
      "testing",
    ],
    [
      ev("exit_criteria_checked", "1 of 1 exit criteria met", { phase: "review", unmet: [] }),
      "Exit criteria of Review: 1 of 1 exit criteria met",
      "neutral",
    ],
    [
      ev("sprint_plan_rejected", "Sprint 1 will be planned again", { reason: "Too big" }),
      "Sprint 1 will be planned again: Too big",
      "danger",
    ],
    [ev("story_unplanned", "Add item"), "Returned “Add item” to the backlog", "neutral"],
    [ev("sprint_replanned", "Sprint 1: Smaller goal"), "Re-planned Sprint 1: Smaller goal", "accent"],
    [
      ev("sprint_planned", "Sprint 2: 7 points committed", {
        number: 2, committed_points: 7, story_ids: [3, 4],
      }),
      "Planned sprint 2: 7 points, 2 stories",
      "accent",
    ],
    [
      ev("process_changed", "Process changed", {
        diff: { capacity: [10, 7], test_first: [false, true] },
      }),
      "Changed the process: capacity 10 → 7, test-first on",
      "accent",
    ],
    [
      ev("story_carried_over", "Delete an item", { story_id: 4, from_sprint_id: 1 }),
      "Moved “Delete an item” back to the backlog for the next sprint",
      "testing",
    ],
    [
      ev("tests_written_first", "Tests written", { story_id: 4 }),
      "Wrote the tests for story #4 before the code",
      "accent",
    ],
    [
      ev("release_created", "v0.1.0", { version: "v0.1.0", story_ids: [1, 2, 3] }),
      "Released v0.1.0 with 3 stories",
      "done",
    ],
    [
      ev("release_created", "v0.2.0", { version: "v0.2.0", story_ids: [5] }),
      "Released v0.2.0 with 1 story",
      "done",
    ],
    [ev("release_exists", "v0.1.0", { version: "v0.1.0" }), "Release v0.1.0 already exists", "neutral"],
    [
      ev("release_skipped", "No sprint to release", { reason: "no sprint" }),
      "Skipped the release: No sprint to release",
      "testing",
    ],
    [
      ev("llm_replay_drift", "", { key: "developer.DeveloperAgent.execution.s1", n: 1 }),
      "The recorded answer for developer.DeveloperAgent.execution.s1 no longer matches the prompt",
      "testing",
    ],
    [
      ev("llm_replay_fallback", "", { key: "scrum_master.StandupAgent.review.s1", n: 1 }),
      "No recorded answer for scrum_master.StandupAgent.review.s1; used the mock instead",
      "testing",
    ],
  ])("%#: %s", (event, text, tone) => {
    expect(describeEvent(event)).toEqual({ text, tone });
  });
});

describe("time", () => {
  it("reads the API's naive timestamps as UTC", () => {
    expect(parseTime("2026-10-16T10:00:00").toISOString()).toBe("2026-10-16T10:00:00.000Z");
    expect(parseTime("2026-10-16T10:00:00+00:00").toISOString()).toBe("2026-10-16T10:00:00.000Z");
  });

  it("formats relative times", () => {
    const now = new Date("2026-10-16T10:00:00Z");
    expect(timeAgo("2026-10-16T09:59:50", now)).toBe("just now");
    expect(timeAgo("2026-10-16T09:55:00", now)).toBe("5 minutes ago");
    expect(timeAgo("2026-10-16T07:00:00", now)).toBe("3 hours ago");
    expect(timeAgo("2026-10-14T10:00:00", now)).toBe("2 days ago");
  });

  it("gives every actor short initials", () => {
    expect(actorInitials("product_owner")).toBe("PO");
    expect(actorInitials("orchestrator")).toBe("OR");
    expect(actorInitials("wizard")).toBe("WI");
  });
});
