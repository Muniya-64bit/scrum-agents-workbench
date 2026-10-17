import type { Phase, ProcessInfo } from "../api/types";
import { describeDiff } from "../lib/process";

/** The sprint's process levers as chips, and the change the retrospective decided for the next. */
export function ProcessChips({ info, phase }: { info: ProcessInfo | null; phase: Phase }) {
  if (!info || info.current_sprint_number === null) return null;
  const { current, next_changes: changes } = info;
  const parts = describeDiff(changes);
  const showNext = parts.length > 0 && (phase === "retro" || phase === "release");

  return (
    <section className="process-bar" aria-label="Sprint process">
      <ul className="process-chips">
        <li className="process-chip">Capacity {current.capacity}</li>
        {current.test_first && <li className="process-chip">Test-first</li>}
        <li className="process-chip">Fix retries {current.max_fix_retries}</li>
        {current.guidelines.length > 0 && (
          <li className="process-chip">
            <details>
              <summary>Agreements ({current.guidelines.length})</summary>
              <ul className="process-agreements">
                {current.guidelines.map((g) => (
                  <li key={g}>{g}</li>
                ))}
              </ul>
            </details>
          </li>
        )}
      </ul>
      {showNext && (
        <p className="process-next" title={info.next_reason || undefined}>
          Next sprint: {parts.join(", ")}
        </p>
      )}
    </section>
  );
}
