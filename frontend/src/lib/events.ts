import type { ActivityEvent, Phase } from "../api/types";
import { describeDiff } from "./process";
import { phaseLabel, roleLabel, statusLabel } from "./scrum";

export type EventTone = "neutral" | "accent" | "done" | "testing" | "danger";

/** Kinds that change the project's phase or gate, so the header must reload. */
export const PHASE_EVENTS = new Set(["phase_started", "approval_requested", "approved", "rejected"]);

/** Who did it, for the avatar and the filter chips. */
export function actorLabel(agent: string): string {
  if (agent === "orchestrator") return "Orchestrator";
  if (agent === "human") return "You";
  return roleLabel(agent);
}

export function actorInitials(agent: string): string {
  const fixed: Record<string, string> = {
    product_owner: "PO",
    scrum_master: "SM",
    architect: "AR",
    developer: "DV",
    qa: "QA",
    devops: "DO",
    human: "You",
    orchestrator: "OR",
  };
  return fixed[agent] ?? agent.slice(0, 2).toUpperCase();
}

/** A sentence for the feed, e.g. `Added story "Create an item"`, and a tone for its marker. */
export function describeEvent(e: ActivityEvent): { text: string; tone: EventTone } {
  const m = e.message;
  const q = (s: string) => `“${s}”`;
  switch (e.kind) {
    case "phase_started":
      return { text: `Started the ${phaseLabel(m as Phase)} phase`, tone: "accent" };
    case "approval_requested":
      return { text: `Waiting for your approval of ${phaseLabel(m as Phase)}`, tone: "testing" };
    case "approved": {
      const phase = phaseLabel(String(e.payload.phase ?? "") as Phase);
      return { text: `Approved ${phase}${m ? `: ${m}` : ""}`, tone: "done" };
    }
    case "rejected": {
      const phase = phaseLabel(String(e.payload.phase ?? "") as Phase);
      return { text: `Rejected ${phase}${m ? `: ${m}` : ""}`, tone: "danger" };
    }
    case "agent_started":
      return { text: `Started working${m ? ` on ${phaseLabel(m as Phase)}` : ""}`, tone: "neutral" };
    case "agent_finished":
      return { text: m || "Finished", tone: "neutral" };
    case "vision_set":
      return { text: `Set the product vision: ${m}`, tone: "neutral" };
    case "epic_created":
      return { text: `Created epic ${q(m)}`, tone: "neutral" };
    case "story_created":
      return { text: `Added story ${q(m)}`, tone: "neutral" };
    case "task_created":
      return { text: `Created task ${q(m)}`, tone: "neutral" };
    case "task_updated": {
      const [title, status] = m.split(" -> ");
      return status
        ? { text: `Moved ${q(title)} to ${statusLabel(status)}`, tone: status === "done" ? "done" : "neutral" }
        : { text: `Updated task ${q(m)}`, tone: "neutral" };
    }
    case "artifact_created": {
      const kind = String(e.payload.artifact_kind ?? "artifact").replace("_", " ");
      return { text: `Wrote ${kind} ${q(m)}`, tone: "neutral" };
    }
    case "bug_reported":
      return { text: `Reported a bug: ${m}`, tone: "danger" };
    case "sprint_planned": {
      const stories = Array.isArray(e.payload.story_ids) ? e.payload.story_ids.length : 0;
      return {
        text: `Planned sprint ${e.payload.number ?? ""}: ${e.payload.committed_points ?? 0} points, ${stories} ${stories === 1 ? "story" : "stories"}`,
        tone: "accent",
      };
    }
    case "process_changed": {
      const parts = describeDiff((e.payload.diff ?? {}) as Record<string, [unknown, unknown]>);
      return { text: `Changed the process: ${parts.join(", ") || "no lever"}`, tone: "accent" };
    }
    case "nfrs_set":
      return { text: `Wrote ${m}`, tone: "neutral" };
    case "backlog_validated":
      return {
        text: `Checked the backlog: ${m}`,
        tone: Array.isArray(e.payload.warnings) && e.payload.warnings.length > 0 ? "testing" : "done",
      };
    case "entry_criteria_checked":
    case "exit_criteria_checked": {
      const which = e.kind.startsWith("entry") ? "Entry" : "Exit";
      const unmet = Array.isArray(e.payload.unmet) ? e.payload.unmet.length : 0;
      return {
        text: `${which} criteria of ${phaseLabel(String(e.payload.phase ?? "") as Phase)}: ${m}`,
        tone: unmet > 0 ? "testing" : "neutral",
      };
    }
    case "sprint_plan_rejected":
      return { text: `${m}${e.payload.reason ? `: ${e.payload.reason}` : ""}`, tone: "danger" };
    case "story_unplanned":
      return { text: `Returned ${q(m)} to the backlog`, tone: "neutral" };
    case "sprint_replanned":
      return { text: `Re-planned ${m}`, tone: "accent" };
    case "story_carried_over":
      return { text: `Moved ${q(m)} back to the backlog for the next sprint`, tone: "testing" };
    case "tests_written_first":
      return { text: `Wrote the tests for story #${e.payload.story_id} before the code`, tone: "accent" };
    case "file_rejected":
      return { text: `Rejected a file with an unsafe or disallowed path: ${m}`, tone: "danger" };
    case "tests_missing":
      return { text: `${m}: QA wrote no usable test file`, tone: "danger" };
    case "maintenance_requested":
      return { text: `Reported a problem after the release: ${q(m)}`, tone: "testing" };
    case "story_refined": {
      const changes = (e.payload.changes ?? {}) as Record<string, [unknown, unknown]>;
      const parts = Object.entries(changes).map(([field, [from, to]]) =>
        field === "acceptance_criteria"
          ? "acceptance criteria"
          : `${field} ${String(from)} → ${String(to)}`,
      );
      return { text: `Refined story ${q(m)}: ${parts.join(", ")}`, tone: "accent" };
    }
    case "backlog_refined":
      return { text: m, tone: e.payload.after === 0 ? "done" : "testing" };
    case "refinement_skipped":
      return { text: m, tone: "neutral" };
    case "agent_message":
      return { text: `Told the ${roleLabel(String(e.payload.to ?? ""))}: ${m}`, tone: "accent" };
    case "tests_revised":
      return { text: `QA rewrote its tests after a mistake in the test code: ${m}`, tone: "accent" };
    case "tests_revision_unchanged":
      return { text: `QA's rewrite changed nothing, so it stopped: ${m}`, tone: "testing" };
    case "docker_build_failed":
      return { text: `The Docker image could not be built: ${m.split("\n")[0]}`, tone: "danger" };
    case "code_skipped":
    case "design_skipped":
      return { text: m, tone: "neutral" };
    case "release_created": {
      const n = Array.isArray(e.payload.story_ids) ? e.payload.story_ids.length : 0;
      return {
        text: `Released ${e.payload.version ?? m} with ${n} ${n === 1 ? "story" : "stories"}`,
        tone: "done",
      };
    }
    case "release_exists":
      return { text: `Release ${e.payload.version ?? m} already exists`, tone: "neutral" };
    case "release_skipped":
      return { text: `Skipped the release: ${m || e.payload.reason}`, tone: "testing" };
    case "llm_replay_drift":
      return {
        text: `The recorded answer for ${e.payload.key} no longer matches the prompt`,
        tone: "testing",
      };
    case "llm_replay_fallback":
      return {
        text: `No recorded answer for ${e.payload.key}; used the mock instead`,
        tone: "testing",
      };
    default:
      return { text: `${humanize(e.kind)}${m ? `: ${m}` : ""}`, tone: "neutral" };
  }
}

function humanize(kind: string): string {
  const s = kind.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** The API stores naive UTC timestamps (no zone); read them as UTC. */
export function parseTime(at: string): Date {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(at) ? at : `${at}Z`);
}

const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

export function timeAgo(at: string, now: Date = new Date()): string {
  const seconds = Math.round((parseTime(at).getTime() - now.getTime()) / 1000);
  const abs = Math.abs(seconds);
  if (abs < 45) return "just now";
  if (abs < 3600) return rtf.format(Math.round(seconds / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(seconds / 3600), "hour");
  return rtf.format(Math.round(seconds / 86400), "day");
}
