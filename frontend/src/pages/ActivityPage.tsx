import { useMemo, useState } from "react";

import { ActivityFeed } from "../components/ActivityFeed";
import { ApprovalCard } from "../components/ApprovalCard";
import { Avatar } from "../components/Avatar";
import { IconSparkle } from "../components/icons";
import { Button, EmptyState, Loading } from "../components/ui";
import { actorLabel } from "../lib/events";
import type { StreamStatus } from "../lib/useEventStream";
import { useProject } from "./ProjectLayout";

const PAGE = 100;

const STATUS_TEXT: Record<StreamStatus, string> = {
  connecting: "Connecting…",
  live: "Live",
  reconnecting: "Reconnecting…",
  error: "Offline",
};

export function ActivityPage() {
  const { project, events, streamStatus, onProjectChange } = useProject();
  const [actor, setActor] = useState<string | null>(null);
  const [limit, setLimit] = useState(PAGE);

  const actors = useMemo(() => [...new Set(events.map((e) => e.agent))], [events]);
  const shown = useMemo(
    () => events.filter((e) => actor === null || e.agent === actor).reverse(),
    [events, actor],
  );

  return (
    <div className="page-body">
      {project.awaiting_approval && <ApprovalCard project={project} onDone={onProjectChange} />}

      <div className="feed-toolbar">
        <div className="chips" role="group" aria-label="Filter by agent">
          <button
            type="button"
            className="chip"
            aria-pressed={actor === null}
            onClick={() => setActor(null)}
          >
            All
          </button>
          {actors.map((a) => (
            <button
              key={a}
              type="button"
              className="chip"
              aria-pressed={actor === a}
              onClick={() => setActor(actor === a ? null : a)}
            >
              <Avatar agent={a} size={18} />
              {actorLabel(a)}
            </button>
          ))}
        </div>
        <span className={`live live-${streamStatus}`} role="status">
          <span className="live-dot" />
          {STATUS_TEXT[streamStatus]}
        </span>
      </div>

      {streamStatus === "connecting" && events.length === 0 ? (
        <Loading label="Loading activity" />
      ) : shown.length === 0 ? (
        <EmptyState icon={<IconSparkle size={22} />} title="No activity yet">
          Start the next phase and the agents' work will appear here as it happens.
        </EmptyState>
      ) : (
        <>
          <ActivityFeed events={shown.slice(0, limit)} />
          {shown.length > limit && (
            <Button variant="ghost" className="feed-more" onClick={() => setLimit(limit + PAGE)}>
              Show older activity ({shown.length - limit} more)
            </Button>
          )}
        </>
      )}
    </div>
  );
}
