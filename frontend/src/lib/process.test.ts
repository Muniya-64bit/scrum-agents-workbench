import { describeDiff, proposedChips } from "./process";
import { nextPhase } from "./scrum";

describe("describeDiff", () => {
  it("names each changed lever in a fixed order", () => {
    expect(
      describeDiff({ test_first: [false, true], capacity: [10, 7], max_fix_retries: [3, 4] }),
    ).toEqual(["capacity 10 → 7", "fix retries 3 → 4", "test-first on"]);
  });

  it("counts working agreements added or removed", () => {
    expect(describeDiff({ guidelines: [[], ["a"]] })).toEqual(["+1 working agreement"]);
    expect(describeDiff({ guidelines: [["a"], ["a", "b", "c"]] })).toEqual(["+2 working agreements"]);
    expect(describeDiff({ guidelines: [["a", "b"], ["b"]] })).toEqual(["−1 working agreement"]);
  });

  it("is empty when nothing changed", () => {
    expect(describeDiff({})).toEqual([]);
  });
});

describe("proposedChips", () => {
  it("turns a retro proposal into short chips and ignores kept levers", () => {
    expect(
      proposedChips({
        capacity: 7,
        max_fix_retries: 2,
        test_first: true,
        add_guidelines: ["Tests first", "  "],
        reason: "x",
      }),
    ).toEqual(["Capacity → 7", "Fix retries → 2", "Test-first on", "+1 guideline"]);
    expect(proposedChips({ capacity: null, test_first: false })).toEqual(["Test-first off"]);
    expect(proposedChips({})).toEqual([]);
  });
});

describe("nextPhase", () => {
  it("goes back to planning after the release only when more sprints follow", () => {
    expect(nextPhase("release")).toBe("done");
    expect(nextPhase("release", true)).toBe("sprint_planning");
    expect(nextPhase("retro", true)).toBe("release");
    expect(nextPhase("done", true)).toBeNull();
  });
});
