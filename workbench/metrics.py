"""Process metrics for the AI Scrum team, defined top-down with Goal-Question-Metric (GQM).

Every number here is computed by replaying the append-only event log (plus the current rows for
titles, points and trace links). Nothing depends on in-memory state or on the order in which the
orchestrator runs the agents, so a metric can always be reproduced from the database.

GQM goals, questions and the metrics that answer them (the `GQM` constant below holds the
exact text that the UI shows):

G1 Improve the predictability of sprint delivery (Scrum Master)
  Q1 How much of what we commit do we deliver?
     committed_points, completed_points, commitment_reliability, carried_over_stories
  Q2 Is the sprint on track while it runs?
     burndown (remaining points over time against an ideal line)
G2 Improve product quality (QA)
  Q3 Does new code pass its tests the first time?
     first_pass_yield, test_pass_rate, test_runs
  Q4 How many defects appear and how costly are they to fix?
     bugs_reported, bugs_open_at_end, fix_attempts, retry_limit_hits, llm_invalid_outputs
G3 Keep requirements traceable (Product Owner)
  Q5 Is every story covered by design, code and tests?
     trace_completeness, ac_coverage
G4 Control the cost of the AI team (the team)
  Q6 What does the AI team cost per unit of delivered work?
     llm_calls, input_tokens, output_tokens, est_cost_usd, cost_per_completed_point

Sprint windows: a sprint's window starts at its `sprint_planned` event and ends at its
`retro_saved` event (or just before the next sprint starts, or at the last event while it is
still running). Events inside the window belong to the sprint. Usage events (`agent_finished`)
that fall between a window's end and the next window's start (retro, release) are charged to that
sprint; usage before the first window (backlog, design) is reported as `unattributed`.

All functions are read-only and never raise on empty data; ratios are `None` when their
denominator is 0. Ratios are rounded to 3 decimals, money to 4, seconds to 3.
"""

import bisect
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from workbench import config
from workbench.db import models as m
from workbench.db import repo

PRICING_SOURCE = (
    "Claude Sonnet 5.5 list price, platform.claude.com/docs/en/models/sonnet-5-5/overview "
    "(checked 2026-10-17)"
)
DESIGN_KINDS = ("architecture", "diagram", "api_spec", "design")
_TEST_FN = re.compile(r"^\s*def test_", re.MULTILINE)
_TASK_KINDS = ("task_created", "task_updated")
_BUG_KINDS = ("bug_reported", "bug_fixed", "bug_fix_failed", "bug_reopened", "bug_verified")

GQM: list[dict] = [
    {
        "id": "G1",
        "goal": "Improve the predictability of sprint delivery",
        "viewpoint": "Scrum Master",
        "questions": [
            {"id": "Q1", "text": "How much of what we commit do we deliver?", "metrics": [
                {"key": "committed_points", "name": "Committed points", "unit": "points",
                 "definition": "Story points of the stories chosen at sprint planning."},
                {"key": "completed_points", "name": "Completed points (velocity)",
                 "unit": "points",
                 "definition": "Story points of committed stories whose tasks are all done "
                               "when the sprint ends."},
                {"key": "commitment_reliability", "name": "Commitment reliability",
                 "unit": "ratio",
                 "definition": "Completed points divided by committed points."},
                {"key": "carried_over_stories", "name": "Carried-over stories", "unit": "count",
                 "definition": "Committed stories that are not done when the sprint ends."},
            ]},
            {"id": "Q2", "text": "Is the sprint on track while it runs?", "metrics": [
                {"key": "burndown", "name": "Burndown", "unit": "points",
                 "definition": "Points still open after each story is completed, compared "
                               "with an ideal straight line from the commitment to zero."},
            ]},
        ],
    },
    {
        "id": "G2",
        "goal": "Improve product quality",
        "viewpoint": "QA",
        "questions": [
            {"id": "Q3", "text": "Does new code pass its tests the first time?", "metrics": [
                {"key": "first_pass_yield", "name": "First-pass yield", "unit": "ratio",
                 "definition": "Stories whose first test run in the sprint passed, divided by "
                               "stories that were tested in the sprint."},
                {"key": "test_pass_rate", "name": "Test pass rate", "unit": "ratio",
                 "definition": "Passed tests divided by all tests in each story's last run of "
                               "the sprint."},
                {"key": "test_runs", "name": "Test runs", "unit": "count",
                 "definition": "Number of test runs for the sprint's stories."},
            ]},
            {"id": "Q4", "text": "How many defects appear and how costly are they to fix?",
             "metrics": [
                {"key": "bugs_reported", "name": "Bugs reported", "unit": "count",
                 "definition": "Bugs QA filed in the sprint for the sprint's stories."},
                {"key": "bugs_open_at_end", "name": "Bugs open at end", "unit": "count",
                 "definition": "Bugs of the sprint's stories that are still open when the "
                               "sprint ends."},
                {"key": "fix_attempts", "name": "Fix attempts", "unit": "count",
                 "definition": "Developer attempts to fix bugs in the sprint (fixed or failed)."},
                {"key": "retry_limit_hits", "name": "Retry-limit hits", "unit": "count",
                 "definition": "Bugs still open at the end of the sprint after the maximum "
                               "number of fix attempts."},
                {"key": "llm_invalid_outputs", "name": "Invalid LLM outputs", "unit": "count",
                 "definition": "Model answers that failed schema validation and were retried."},
            ]},
        ],
    },
    {
        "id": "G3",
        "goal": "Keep requirements traceable",
        "viewpoint": "Product Owner",
        "questions": [
            {"id": "Q5", "text": "Is every story covered by design, code and tests?", "metrics": [
                {"key": "trace_completeness", "name": "Trace completeness", "unit": "ratio",
                 "definition": "Sprint stories linked to at least one design, one code and one "
                               "test artifact, divided by sprint stories."},
                {"key": "ac_coverage", "name": "Acceptance-criteria coverage", "unit": "ratio",
                 "definition": "Test functions (at most one per criterion) divided by "
                               "acceptance criteria of the sprint's stories."},
            ]},
        ],
    },
    {
        "id": "G4",
        "goal": "Control the cost of the AI team",
        "viewpoint": "the team",
        "questions": [
            {"id": "Q6", "text": "What does the AI team cost per unit of delivered work?",
             "metrics": [
                {"key": "llm_calls", "name": "LLM calls", "unit": "count",
                 "definition": "Model API calls made by the agents in the sprint (cache hits "
                               "and mock answers are free and not counted)."},
                {"key": "input_tokens", "name": "Input tokens", "unit": "tokens",
                 "definition": "Prompt tokens sent to the model in the sprint."},
                {"key": "output_tokens", "name": "Output tokens", "unit": "tokens",
                 "definition": "Tokens the model produced in the sprint."},
                {"key": "est_cost_usd", "name": "Estimated cost", "unit": "usd",
                 "definition": "Tokens times the configured price per million tokens."},
                {"key": "cost_per_completed_point", "name": "Cost per completed point",
                 "unit": "usd",
                 "definition": "Estimated cost divided by completed points."},
            ]},
        ],
    },
]


# --- pricing -----------------------------------------------------------------------------------


def pricing() -> dict:
    return {"model": config.MODEL, "input_per_mtok": config.LLM_PRICE_INPUT_PER_MTOK,
            "output_per_mtok": config.LLM_PRICE_OUTPUT_PER_MTOK, "source": PRICING_SOURCE}


def cost(input_tokens: int, output_tokens: int) -> float:
    usd = (input_tokens * config.LLM_PRICE_INPUT_PER_MTOK
           + output_tokens * config.LLM_PRICE_OUTPUT_PER_MTOK) / 1_000_000
    return round(usd, 4)


def _ratio(num: float, den: float) -> float | None:
    return round(num / den, 3) if den else None


# --- events and windows ------------------------------------------------------------------------


def _events(db: Session, project_id: int, kinds: tuple[str, ...] | list[str] | None = None,
            start_id: int | None = None, end_id: int | None = None) -> list[m.Event]:
    q = select(m.Event).where(m.Event.project_id == project_id)
    if kinds:
        q = q.where(m.Event.kind.in_(kinds))
    if start_id is not None:
        q = q.where(m.Event.id >= start_id)
    if end_id is not None:
        q = q.where(m.Event.id <= end_id)
    return list(db.scalars(q.order_by(m.Event.id)))


@dataclass(frozen=True)
class Window:
    sprint_id: int
    number: int
    start_id: int
    end_id: int
    start_at: datetime
    end_at: datetime
    closed: bool
    usage_end_id: int = 0  # last event id whose LLM usage is charged to this sprint

    @property
    def duration_s(self) -> float:
        return round(max((self.end_at - self.start_at).total_seconds(), 0.0), 3)


def _build_windows(sprints: list[m.Sprint], events: list[m.Event]) -> list[Window]:
    if not sprints:
        return []
    now = datetime.now(UTC).replace(tzinfo=None)
    ids = [e.id for e in events]
    at = {e.id: e.created_at for e in events}
    planned: dict[int, m.Event] = {}
    created: dict[int, m.Event] = {}
    retro: dict[int, list[m.Event]] = {}
    for e in events:
        sid = (e.payload or {}).get("sprint_id")
        if e.kind == "sprint_planned":
            planned[sid] = e  # the latest one wins
        elif e.kind == "sprint_created":
            created.setdefault(sid, e)
        elif e.kind == "retro_saved":
            retro.setdefault(sid, []).append(e)
    first_id = ids[0] if ids else 0
    starts = []
    for s in sprints:
        ev = planned.get(s.id) or created.get(s.id)
        starts.append(ev.id if ev else first_id)
    last_id = ids[-1] if ids else 0

    def at_or_before(event_id: int, floor: int) -> datetime:
        i = bisect.bisect_right(ids, event_id) - 1
        return at[ids[i]] if i >= 0 and ids[i] >= floor else at.get(floor, now)

    windows = []
    for i, s in enumerate(sprints):
        start = starts[i]
        start_at = at.get(start, now)
        nxt = starts[i + 1] if i + 1 < len(sprints) else None
        usage_end = max(nxt - 1, start) if nxt is not None else max(last_id, start)
        done = next((e for e in retro.get(s.id, []) if e.id >= start), None)
        if done is not None:
            end, end_at, closed = done.id, done.created_at, True
        elif nxt is not None:
            end = max(nxt - 1, start)
            end_at, closed = at_or_before(end, start), True
        else:
            end, end_at, closed = max(last_id, start), at_or_before(last_id, start), False
        windows.append(Window(s.id, s.number, start, end, start_at, max(end_at, start_at),
                              closed, usage_end))
    return windows


def sprint_windows(db: Session, project_id: int) -> list[Window]:
    return _build_windows(repo.sprints(db, project_id), _events(db, project_id))


# --- shared, loaded-once view of a project ------------------------------------------------------


@dataclass
class _Ctx:
    db: Session
    project_id: int
    sprints: list[m.Sprint]
    events: list[m.Event]
    windows: dict[int, Window]
    stories: dict[int, m.UserStory]
    tasks_by_story: dict[int, list[int]]
    bug_story: dict[int, int]
    arts_by_story: dict[int, list[m.Artifact]]

    @classmethod
    def load(cls, db: Session, project_id: int) -> "_Ctx":
        sprints = repo.sprints(db, project_id)
        events = _events(db, project_id)
        tasks_by_story: dict[int, list[int]] = {}
        for t in repo.tasks(db, project_id):
            tasks_by_story.setdefault(t.story_id, []).append(t.id)
        arts: dict[int, list[m.Artifact]] = {}
        for link, art in repo.trace_links(db, project_id):
            arts.setdefault(link.story_id, []).append(art)
        return cls(db, project_id, sprints, events,
                   {w.sprint_id: w for w in _build_windows(sprints, events)},
                   {s.id: s for s in repo.backlog(db, project_id)}, tasks_by_story,
                   {b.id: b.story_id for b in repo.bugs(db, project_id)}, arts)

    def window(self, sprint: m.Sprint) -> Window:
        return self.windows[sprint.id]

    def in_window(self, w: Window, kinds: tuple[str, ...] | str) -> list[m.Event]:
        kinds = (kinds,) if isinstance(kinds, str) else kinds
        return [e for e in self.events if e.kind in kinds and w.start_id <= e.id <= w.end_id]

    def bug_story_of(self, e: m.Event) -> int | None:
        p = e.payload or {}
        return p.get("story_id") or self.bug_story.get(p.get("bug_id")) \
            or _story_of_bug(self.db, p.get("bug_id"))


def _story_of_bug(db: Session, bug_id: int | None) -> int | None:
    bug = db.get(m.Bug, bug_id) if bug_id else None
    return bug.story_id if bug else None


# --- plan snapshot -----------------------------------------------------------------------------


def _plan(ctx: _Ctx, sprint: m.Sprint) -> dict:
    planned = None
    for e in ctx.events:
        if e.kind == "sprint_planned" and (e.payload or {}).get("sprint_id") == sprint.id:
            planned = e
    if planned is not None:
        p = planned.payload
        story_ids = list(p.get("story_ids") or [])
        points = sum(ctx.stories[s].points for s in story_ids if s in ctx.stories)
        return {"story_ids": story_ids,
                "committed_points": p.get("committed_points", points),
                "capacity": p.get("capacity", sprint.capacity),
                "process": dict(p.get("process") or {}),
                "process_changes": dict(p.get("process_changes") or {}),
                "process_reason": p.get("process_reason") or ""}
    story_ids = []
    for e in ctx.events:
        p = e.payload or {}
        if (e.kind == "story_planned" and p.get("sprint_id") == sprint.id
                and p.get("story_id") not in story_ids):
            story_ids.append(p.get("story_id"))
    return {"story_ids": story_ids,
            "committed_points": sum(ctx.stories[s].points for s in story_ids if s in ctx.stories),
            "capacity": sprint.capacity, "process": {}, "process_changes": {},
            "process_reason": ""}


def sprint_plan(db: Session, sprint: m.Sprint) -> dict:
    """What was committed: from the `sprint_planned` event, else rebuilt from `story_planned`."""
    return _plan(_Ctx.load(db, sprint.project_id), sprint)


# --- task-state replay -------------------------------------------------------------------------


def _task_status(e: m.Event) -> str | None:
    status = (e.payload or {}).get("status")
    if status:
        return status
    if " -> " in e.message:  # events written before the payload carried the status
        return e.message.rsplit(" -> ", 1)[1].strip()
    return None


def _apply_task_event(status: dict[int, str], known: set[int], e: m.Event) -> None:
    tid = (e.payload or {}).get("task_id")
    if tid not in known:
        return
    if e.kind == "task_created":
        status[tid] = "todo"
    elif (new := _task_status(e)) is not None:
        status[tid] = new


def _replay_tasks(db: Session, project_id: int, until_id: int) -> dict[int, str]:
    """Task id -> status after every task event up to `until_id`."""
    known = {t.id for t in repo.tasks(db, project_id)}
    status: dict[int, str] = {}
    for e in _events(db, project_id, _TASK_KINDS, end_id=until_id):
        _apply_task_event(status, known, e)
    return status


def _done_from(status: dict[int, str], tasks_by_story: dict[int, list[int]],
               story_ids) -> set[int]:
    done = set()
    for sid in story_ids:
        states = [status[t] for t in tasks_by_story.get(sid, []) if t in status]
        if states and all(s == "done" for s in states):
            done.add(sid)
    return done


def _done_stories(status_by_task: dict[int, str], story_ids, db: Session) -> set[int]:
    """Stories with at least one task in the replay and every task done."""
    tasks_by_story: dict[int, list[int]] = {}
    for t in db.scalars(select(m.Task).where(m.Task.story_id.in_(list(story_ids)))):
        tasks_by_story.setdefault(t.story_id, []).append(t.id)
    return _done_from(status_by_task, tasks_by_story, story_ids)


def _status_at(ctx: _Ctx, until_id: int) -> dict[int, str]:
    known = {t for ts in ctx.tasks_by_story.values() for t in ts}
    status: dict[int, str] = {}
    for e in ctx.events:
        if e.id > until_id:
            break
        if e.kind in _TASK_KINDS:
            _apply_task_event(status, known, e)
    return status


# --- burndown ----------------------------------------------------------------------------------


def _burndown(ctx: _Ctx, sprint: m.Sprint) -> dict:
    plan, w = _plan(ctx, sprint), ctx.window(sprint)
    committed = plan["committed_points"]
    planned = plan["story_ids"]
    points = {sid: ctx.stories[sid].points for sid in planned if sid in ctx.stories}
    title = {sid: ctx.stories[sid].title for sid in planned if sid in ctx.stories}
    known = {t for ts in ctx.tasks_by_story.values() for t in ts}

    status = _status_at(ctx, w.start_id)
    done = _done_from(status, ctx.tasks_by_story, planned)

    def remaining() -> float:
        return committed - sum(points.get(s, 0) for s in done)

    series = [{"t": 0.0, "step": 0, "at": w.start_at, "remaining": remaining(),
               "story_id": None, "label": "Sprint start"}]
    for e in ctx.events:
        if e.id <= w.start_id or e.id > w.end_id or e.kind not in _TASK_KINDS:
            continue
        _apply_task_event(status, known, e)
        now_done = _done_from(status, ctx.tasks_by_story, planned)
        changed = now_done ^ done
        done = now_done
        for sid in sorted(changed):
            verb = "Done" if sid in done else "Reopened"
            series.append({
                "t": round(max((e.created_at - w.start_at).total_seconds(), 0.0), 3),
                "step": len(series), "at": e.created_at, "remaining": remaining(),
                "story_id": sid, "label": f"{verb}: {title.get(sid, f'story {sid}')}"})
    final = remaining()
    duration = w.duration_s
    series.append({"t": duration, "step": len(series), "at": w.end_at, "remaining": final,
                   "story_id": None, "label": "Sprint end" if w.closed else "Now"})
    ideal = [{"t": 0.0, "remaining": committed},
             {"t": max(duration, 1e-3), "remaining": 0}]
    return {"sprint_id": sprint.id, "sprint_number": sprint.number,
            "committed_points": committed, "remaining_points": final,
            "duration_s": duration, "closed": w.closed, "series": series, "ideal": ideal}


def burndown(db: Session, sprint: m.Sprint) -> dict:
    """Points left over time, rebuilt from task events; independent of stand-up snapshots."""
    return _burndown(_Ctx.load(db, sprint.project_id), sprint)


# --- traceability helpers ----------------------------------------------------------------------


def _test_functions(content: str) -> int:
    return len(_TEST_FN.findall(content or ""))


def _latest_artifacts_by_path(arts, kinds) -> dict[str, m.Artifact]:
    """Newest version (highest id) of each distinct path among artifacts of the given kinds."""
    latest: dict[str, m.Artifact] = {}
    for a in arts:
        if a.kind in kinds:
            key = a.path or a.name
            if key not in latest or a.id > latest[key].id:
                latest[key] = a
    return latest


def _story_test_count(ctx: _Ctx, story_id: int) -> int:
    latest = _latest_artifacts_by_path(ctx.arts_by_story.get(story_id, []), ("test",))
    return sum(_test_functions(a.content) for a in latest.values())


def test_function_count(db: Session, project_id: int, story_id: int) -> int:
    """Test functions in the latest version of each test file traced to the story."""
    return _story_test_count(_Ctx.load(db, project_id), story_id)


test_function_count.__test__ = False  # not a pytest test


def _is_complete(arts: list[m.Artifact]) -> bool:
    kinds = {a.kind for a in arts}
    return bool(kinds & set(DESIGN_KINDS)) and "code" in kinds and "test" in kinds


# --- per-sprint metrics ------------------------------------------------------------------------


def _usage(events: list[m.Event]) -> dict:
    total = Counter()
    for e in events:
        p = e.payload or {}
        for k in ("calls", "input_tokens", "output_tokens", "cache_hits", "invalid_outputs"):
            total[k] += int(p.get(k) or 0)
    return dict(total)


def _sprint_metrics(ctx: _Ctx, sprint: m.Sprint) -> dict:
    plan, w = _plan(ctx, sprint), ctx.window(sprint)
    planned = set(plan["story_ids"])
    points = {sid: ctx.stories[sid].points for sid in planned if sid in ctx.stories}
    committed = plan["committed_points"]
    done = _done_from(_status_at(ctx, w.end_id), ctx.tasks_by_story, planned)
    completed = sum(points.get(s, 0) for s in done)

    runs = [e for e in ctx.in_window(w, "test_run") if e.payload.get("story_id") in planned]
    first: dict[int, m.Event] = {}
    last: dict[int, m.Event] = {}
    for e in runs:
        first.setdefault(e.payload["story_id"], e)
        last[e.payload["story_id"]] = e
    passed = sum(int(e.payload.get("passed") or 0) for e in last.values())
    failed = sum(int(e.payload.get("failed") or 0) for e in last.values())

    # bug state replayed up to the end of the window
    bug_status: dict[int, str] = {}
    attempts: Counter = Counter()
    for e in ctx.events:
        if e.id > w.end_id:
            break
        if e.kind not in _BUG_KINDS:
            continue
        bid = e.payload.get("bug_id")
        if e.kind in ("bug_reported", "bug_reopened"):
            bug_status[bid] = "open"
        elif e.kind in ("bug_fixed", "bug_verified"):
            bug_status[bid] = "fixed"
        if e.kind in ("bug_fixed", "bug_fix_failed"):
            attempts[bid] += 1

    def in_plan(e: m.Event) -> bool:
        return ctx.bug_story_of(e) in planned

    reported = [e for e in ctx.in_window(w, "bug_reported") if in_plan(e)]
    verified = [e for e in ctx.in_window(w, "bug_verified") if in_plan(e)]
    tried = [e for e in ctx.in_window(w, ("bug_fixed", "bug_fix_failed")) if in_plan(e)]
    open_bugs = [bid for bid, st in bug_status.items()
                 if st == "open" and ctx.bug_story.get(bid) in planned]
    process = plan["process"]
    limit = process.get("max_fix_retries") or config.DEFAULT_MAX_FIX_RETRIES
    limit_hits = sum(1 for bid in open_bugs if attempts[bid] >= limit)

    usage = _usage([e for e in ctx.events
                    if e.kind == "agent_finished" and w.start_id <= e.id <= w.usage_end_id])
    spend = cost(usage.get("input_tokens", 0), usage.get("output_tokens", 0))

    complete = sum(1 for s in planned if _is_complete(ctx.arts_by_story.get(s, [])))
    ac_total = sum(len(ctx.stories[s].acceptance_criteria or []) for s in planned
                   if s in ctx.stories)
    ac_covered = sum(min(_story_test_count(ctx, s), len(ctx.stories[s].acceptance_criteria or []))
                     for s in planned if s in ctx.stories)

    return {
        "sprint_id": sprint.id, "sprint_number": sprint.number, "goal": sprint.goal,
        "closed": w.closed,
        "committed_points": committed, "committed_stories": len(planned),
        "completed_points": completed, "completed_stories": len(done),
        "commitment_reliability": _ratio(completed, committed),
        "carried_over_stories": len(planned) - len(done),
        "test_runs": len(runs),
        "first_pass_yield": _ratio(sum(1 for e in first.values() if e.payload.get("ok")),
                                   len(first)),
        "test_pass_rate": _ratio(passed, passed + failed),
        "bugs_reported": len(reported), "bugs_fixed_in_sprint": len(verified),
        "bugs_open_at_end": len(open_bugs), "fix_attempts": len(tried),
        "retry_limit_hits": limit_hits,
        "llm_calls": usage.get("calls", 0), "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "cache_hits": usage.get("cache_hits", 0),
        "llm_invalid_outputs": usage.get("invalid_outputs", 0),
        "est_cost_usd": spend,
        "cost_per_completed_point": _ratio(spend, completed) if completed else None,
        "trace_completeness": _ratio(complete, len(planned)),
        "ac_coverage": _ratio(ac_covered, ac_total),
        "duration_s": w.duration_s, "process": process,
    }


def sprint_metrics(db: Session, sprint: m.Sprint) -> dict:
    return _sprint_metrics(_Ctx.load(db, sprint.project_id), sprint)


# --- project metrics ---------------------------------------------------------------------------


def project_metrics(db: Session, project_id: int) -> dict:
    ctx = _Ctx.load(db, project_id)
    sprints = [_sprint_metrics(ctx, s) for s in ctx.sprints]
    finished = [e for e in ctx.events if e.kind == "agent_finished"]
    attributed = {e.id for w in ctx.windows.values() for e in finished
                  if w.start_id <= e.id <= w.usage_end_id}
    unattributed = _usage([e for e in finished if e.id not in attributed])
    total = _usage(finished)
    stories = list(ctx.stories.values())
    planned = {sid for s in ctx.sprints for sid in _plan(ctx, s)["story_ids"]}
    closed = [s for s in sprints if s["closed"]]
    code = _latest_artifacts_by_path(repo.artifacts(db, project_id, "code"), ("code",))
    modes = sorted({str(e.payload["llm_mode"]) for e in finished if e.payload.get("llm_mode")})
    un_in, un_out = unattributed.get("input_tokens", 0), unattributed.get("output_tokens", 0)
    return {
        "project": {
            "stories_total": len(stories),
            "stories_done": sum(1 for s in stories if repo.story_is_done(s)),
            "points_total": sum(s.points for s in stories),
            "points_done": sum(s.points for s in stories if repo.story_is_done(s)),
            "sprint_count": len(sprints),
            "avg_velocity": (round(sum(s["completed_points"] for s in closed) / len(closed), 3)
                             if closed else None),
            "total_llm_calls": total.get("calls", 0),
            "total_input_tokens": total.get("input_tokens", 0),
            "total_output_tokens": total.get("output_tokens", 0),
            "total_cost_usd": cost(total.get("input_tokens", 0), total.get("output_tokens", 0)),
            "llm_modes": modes,
            "loc": sum(len((a.content or "").splitlines()) for a in code.values()),
            "trace_completeness": _ratio(
                sum(1 for s in planned if _is_complete(ctx.arts_by_story.get(s, []))),
                len(planned)),
        },
        "sprints": sprints,
        "unattributed": {"llm_calls": unattributed.get("calls", 0), "input_tokens": un_in,
                         "output_tokens": un_out, "est_cost_usd": cost(un_in, un_out)},
        "gqm": GQM,
        "pricing": pricing(),
    }
