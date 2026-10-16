"""Server-Sent Events stream of a project's activity feed.

The Event table is the source of truth, so the stream polls it for rows newer than the last one
sent. Clients reconnect with the `Last-Event-ID` header (EventSource does this automatically) and
pick up exactly where they left off."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable

from sqlalchemy.orm import Session

from workbench.api.views import EventView
from workbench.db import repo

KEEPALIVE_SECONDS = 15.0


def event_view(e) -> EventView:
    return EventView(id=e.id, agent=e.agent, kind=e.kind, message=e.message,
                     payload=e.payload, at=e.created_at)


def format_sse(e) -> str:
    return f"id: {e.id}\ndata: {event_view(e).model_dump_json()}\n\n"


def _fetch(session_factory: Callable[[], Session], project_id: int, after: int) -> list:
    with session_factory() as db:
        return repo.events_since(db, project_id, after)


async def event_stream(
    session_factory: Callable[[], Session],
    project_id: int,
    after: int,
    is_disconnected: Callable[[], Awaitable[bool]],
    poll_seconds: float = 1.0,
) -> AsyncIterator[str]:
    """Yield SSE frames for events with id > `after` until the client disconnects."""
    last, idle = after, 0.0
    while not await is_disconnected():
        events = await asyncio.to_thread(_fetch, session_factory, project_id, last)
        for e in events:
            last = e.id
            yield format_sse(e)
        idle = 0.0 if events else idle + poll_seconds
        if idle >= KEEPALIVE_SECONDS:
            idle = 0.0
            yield ": keep-alive\n\n"
        await asyncio.sleep(poll_seconds)
