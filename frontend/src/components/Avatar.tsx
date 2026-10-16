import { actorInitials, actorLabel } from "../lib/events";

/** Round badge in the agent's role color with its initials, e.g. "PO" for Product Owner. */
export function Avatar({ agent, size = 28 }: { agent: string; size?: number }) {
  return (
    <span
      className={`avatar avatar-${agent}`}
      style={{ width: size, height: size, fontSize: size * 0.36 }}
      title={actorLabel(agent)}
      aria-hidden="true"
    >
      {actorInitials(agent)}
    </span>
  );
}
