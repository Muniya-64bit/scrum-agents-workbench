import { useEffect, useRef, useState } from "react";

import { api, streamUrl } from "../api/client";
import type { ActivityEvent } from "../api/types";

export type StreamStatus = "connecting" | "live" | "reconnecting" | "error";

const MAX_EVENTS = 500; // keep memory bounded on long runs

/**
 * The project's activity: history from GET /events, then new events live from the SSE stream.
 * `onNew` fires only for events that arrive after the history, so callers can react to change
 * (reload data, show a toast) without replaying the past. EventSource reconnects by itself and
 * resumes after the last event id it saw.
 */
export function useEventStream(projectId: number, onNew?: (e: ActivityEvent) => void) {
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [status, setStatus] = useState<StreamStatus>("connecting");
  const onNewRef = useRef(onNew);
  onNewRef.current = onNew;

  useEffect(() => {
    let source: EventSource | undefined;
    let closed = false;
    setEvents([]);
    setStatus("connecting");

    api
      .events(projectId)
      .then((history) => {
        if (closed) return;
        setEvents(history.slice(-MAX_EVENTS));
        const last = history.length ? history[history.length - 1].id : 0;
        source = new EventSource(streamUrl(projectId, last));
        source.onopen = () => setStatus("live");
        source.onerror = () => setStatus(source?.readyState === 2 ? "error" : "reconnecting");
        source.onmessage = (msg: MessageEvent<string>) => {
          const e = JSON.parse(msg.data) as ActivityEvent;
          setEvents((prev) => (prev.some((p) => p.id === e.id) ? prev : [...prev, e].slice(-MAX_EVENTS)));
          setStatus("live");
          onNewRef.current?.(e);
        };
      })
      .catch(() => {
        if (!closed) setStatus("error");
      });

    return () => {
      closed = true;
      source?.close();
    };
  }, [projectId]);

  return { events, status };
}
