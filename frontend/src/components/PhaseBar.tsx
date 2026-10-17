import { useEffect, useRef } from "react";

import type { Phase } from "../api/types";
import { GATES, PHASES, SPRINT_PHASES } from "../lib/scrum";
import { IconCheck } from "./icons";

/** The Scrum lifecycle as a stepper: finished phases ticked, current phase highlighted. */
export function PhaseBar({
  phase,
  awaitingApproval,
  sprintNumber = null,
}: {
  phase: Phase;
  awaitingApproval: boolean;
  /** The current sprint, shown next to the current phase while a sprint is running. */
  sprintNumber?: number | null;
}) {
  const current = PHASES.findIndex((p) => p.id === phase);
  const listRef = useRef<HTMLOListElement>(null);

  // On narrow screens the bar scrolls sideways; keep the current phase in view.
  useEffect(() => {
    const list = listRef.current;
    const el = list?.querySelector<HTMLElement>('[aria-current="step"]');
    if (list && el && list.scrollWidth > list.clientWidth) {
      list.scrollLeft = el.offsetLeft - list.clientWidth / 2 + el.clientWidth / 2;
    }
  }, [phase]);

  return (
    <ol className="phasebar" aria-label="Project phase" ref={listRef}>
      {PHASES.map((p, i) => {
        const state = i < current || phase === "done" ? "past" : i === current ? "current" : "future";
        const gate = GATES.includes(p.id);
        return (
          <li
            key={p.id}
            className={`phase phase-${state} ${state === "current" && awaitingApproval ? "phase-waiting" : ""}`}
            aria-current={state === "current" ? "step" : undefined}
          >
            <span className="phase-marker">{state === "past" ? <IconCheck size={12} /> : i + 1}</span>
            <span className="phase-label">
              {p.label}
              {gate && (
                <span className="phase-gate" title="Needs human approval">
                  gate
                </span>
              )}
              {state === "current" && sprintNumber !== null && SPRINT_PHASES.includes(p.id) && (
                <span className="phase-sprint">Sprint {sprintNumber}</span>
              )}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
