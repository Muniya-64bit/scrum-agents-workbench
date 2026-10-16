import { useEffect, useState } from "react";

import type { ActivityEvent, Phase } from "../api/types";
import { actorLabel, describeEvent, parseTime, timeAgo } from "../lib/events";
import { phaseLabel } from "../lib/scrum";
import { Avatar } from "./Avatar";

/** Re-render every 30 s so "2 minutes ago" stays true. */
function useNow(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(id);
  }, []);
  return now;
}

/** Events newest first. Phase changes are shown as dividers between the agent messages. */
export function ActivityFeed({ events }: { events: ActivityEvent[] }) {
  const now = useNow();
  return (
    <ol className="feed" aria-label="Activity">
      {events.map((e) =>
        e.kind === "phase_started" ? (
          <li key={e.id} className="feed-divider">
            <span>{phaseLabel(e.message as Phase)} phase</span>
            <time dateTime={parseTime(e.at).toISOString()} title={parseTime(e.at).toLocaleString()}>
              {timeAgo(e.at, now)}
            </time>
          </li>
        ) : (
          <FeedItem key={e.id} event={e} now={now} />
        ),
      )}
    </ol>
  );
}

function FeedItem({ event, now }: { event: ActivityEvent; now: Date }) {
  const { text, tone } = describeEvent(event);
  const at = parseTime(event.at);
  return (
    <li className={`feed-item feed-${tone}`}>
      <Avatar agent={event.agent} />
      <div className="feed-body">
        <p className="feed-text">
          <strong>{actorLabel(event.agent)}</strong> {text}
        </p>
      </div>
      <time className="feed-time" dateTime={at.toISOString()} title={at.toLocaleString()}>
        {timeAgo(event.at, now)}
      </time>
    </li>
  );
}
