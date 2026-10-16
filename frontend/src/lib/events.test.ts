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
    [ev("code_committed", "Story #3: Add"), "Code committed: Story #3: Add", "neutral"],
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
