import type { ProcessDiff, ProposedChanges } from "../api/types";

const LEVER_ORDER = ["capacity", "max_fix_retries", "test_first", "guidelines"] as const;

/** The changed levers of a process diff in words, e.g. ["capacity 10 → 7", "test-first on"]. */
export function describeDiff(diff: ProcessDiff): string[] {
  const parts: string[] = [];
  for (const lever of LEVER_ORDER) {
    const pair = diff[lever];
    if (!pair) continue;
    const [before, after] = pair;
    if (lever === "capacity") parts.push(`capacity ${before} → ${after}`);
    else if (lever === "max_fix_retries") parts.push(`fix retries ${before} → ${after}`);
    else if (lever === "test_first") parts.push(`test-first ${after ? "on" : "off"}`);
    else {
      const added = (Array.isArray(after) ? after.length : 0) - (Array.isArray(before) ? before.length : 0);
      parts.push(`${added >= 0 ? "+" : "−"}${Math.abs(added)} working ${Math.abs(added) === 1 ? "agreement" : "agreements"}`);
    }
  }
  return parts;
}

/** The levers a retrospective proposes, as short chips: "Capacity → 7", "Test-first on". */
export function proposedChips(p: ProposedChanges): string[] {
  const chips: string[] = [];
  if (p.capacity != null) chips.push(`Capacity → ${p.capacity}`);
  if (p.max_fix_retries != null) chips.push(`Fix retries → ${p.max_fix_retries}`);
  if (p.test_first != null) chips.push(`Test-first ${p.test_first ? "on" : "off"}`);
  const added = p.add_guidelines?.filter((g) => g.trim()).length ?? 0;
  if (added > 0) chips.push(`+${added} ${added === 1 ? "guideline" : "guidelines"}`);
  return chips;
}
