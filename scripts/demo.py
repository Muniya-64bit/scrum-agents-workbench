"""Run, serve or record a canned demo scenario (docs/demo.md).

    python scripts/demo.py run --scenario todo-app --fresh          # idea -> done, offline
    python scripts/demo.py run --scenario todo-app --fresh --step   # pause after every phase
    python scripts/demo.py serve --scenario todo-app --fresh        # API for the UI (:8000)
    python scripts/demo.py record --scenario todo-app               # real model, costs money

A scenario is a directory `demo/scenarios/<name>` with `scenario.json` and `calls/*.json` (the
LLM answers, keyed by meaning). The run uses its own database and workspace under `demo_runs/`,
never `./workbench.db` or `./workspaces`. The environment is set BEFORE `workbench` is imported,
because the settings are read at import time."""

import argparse
import json
import os
import shutil
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = ROOT / "demo" / "scenarios"
RUNS = ROOT / "demo_runs"
MODES = ("replay", "record", "mock", "live")


def load_scenario(name: str) -> tuple[Path, dict]:
    folder = SCENARIOS / name
    try:
        return folder, json.loads((folder / "scenario.json").read_text(encoding="utf-8"))
    except OSError:
        known = ", ".join(sorted(p.name for p in SCENARIOS.iterdir() if p.is_dir()))
        raise SystemExit(f"No scenario '{name}' in {SCENARIOS} (known: {known})") from None


def _force_remove(func, path, _exc):
    """git marks its objects read-only; on Windows deleting them needs a chmod first."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def remove_run(name: str) -> None:
    for target in (RUNS / f"{name}.db", RUNS / f"{name}-workspaces"):
        if target.is_dir():
            shutil.rmtree(target, onexc=_force_remove)
        elif target.exists():
            target.unlink()


def configure(name: str, mode: str, fresh: bool) -> dict:
    """Set the environment for a run of scenario `name` and return the scenario data.

    Variables already set in the shell win over the scenario's `env` (so a smoke test can
    shrink MAX_SPRINTS); `--mode` and the run's paths always win."""
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    folder, scenario = load_scenario(name)
    if mode == "record":  # never overwrite the scripted scenario
        folder = SCENARIOS / f"{name}-recorded"
    if fresh:
        remove_run(name)
    RUNS.mkdir(exist_ok=True)
    for key, value in (scenario.get("env") or {}).items():
        os.environ.setdefault(key, str(value))
    os.environ["LLM_MODE"] = mode
    os.environ["LLM_SCENARIO_DIR"] = str(folder)
    os.environ.setdefault("LLM_REPLAY_FALLBACK", scenario.get("fallback", "error"))
    os.environ["DATABASE_URL"] = f"sqlite:///{(RUNS / f'{name}.db').as_posix()}"
    os.environ["WORKSPACES_DIR"] = str(RUNS / f"{name}-workspaces")
    scenario["_dir"] = str(folder)
    return scenario


def _agents():
    from workbench.agents.registry import AGENTS

    return AGENTS


def reset_replay() -> None:
    """Every LLM client starts counting calls from 1 (a new run of the same scenario)."""
    seen = set()
    for agent in _agents().values():
        for owner in (agent, getattr(agent, "builder", None)):
            llm = getattr(owner, "llm", None)
            if llm is not None and id(llm) not in seen:
                seen.add(id(llm))
                llm.reset_replay()


def open_project(scenario: dict, fresh: bool):
    """The scenario's project in the run database; creates it on a fresh database."""
    from workbench.db import repo
    from workbench.db.session import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    projects = repo.list_projects(db)
    if projects and not fresh:
        db.close()
        raise SystemExit(
            "The demo database already has a project. Its replay position is lost, so start "
            "again with --fresh.")
    if projects:
        return db, projects[0]
    return db, repo.create_project(db, scenario["project_name"], scenario["idea"])


# --- run ----------------------------------------------------------------------------------------

HIGHLIGHTS = ("code_committed", "tests_committed", "tests_written_first", "test_run",
              "bug_reported", "bug_fixed", "bug_fix_failed", "bug_verified", "bug_reopened",
              "bugs_left_open", "story_carried_over", "process_changed", "release_created",
              "llm_replay_fallback", "llm_replay_drift")


def phase_summary(db, project_id: int, since: int) -> str:
    from collections import Counter

    from workbench.db import repo

    events = repo.events_since(db, project_id, since)
    counts = Counter(e.kind for e in events)
    parts = [f"{counts[k]} {k}" for k in HIGHLIGHTS if counts[k]]
    for e in events:
        if e.kind in ("process_changed", "release_created", "story_carried_over"):
            parts.append(f"  - {e.message}")
    return f"  {len(events)} events: " + ", ".join(p for p in parts if not p.startswith("  -")) + \
        "".join("\n" + p for p in parts if p.startswith("  -"))


def run_project(db, project, step: bool) -> None:
    from workbench.db import repo
    from workbench.orchestrator.engine import MAX_STEPS, Orchestrator

    orch = Orchestrator(db, _agents())
    for _ in range(MAX_STEPS):
        if project.phase == "done":
            return
        since = max((e.id for e in repo.events_since(db, project.id)), default=0)
        orch.step(project.id)
        print(f"[{project.phase}]" + ("  (waiting for approval)" if project.awaiting_approval
                                      else ""))
        if step:
            print(phase_summary(db, project.id, since))
            input("  Press Enter to continue... ")
        if project.awaiting_approval:
            orch.approve(project.id)
    raise SystemExit(f"The project did not finish within {MAX_STEPS} steps")


def print_summary(db, project) -> None:
    from workbench import metrics
    from workbench.db import models as m
    from workbench.db import repo
    from workbench.workspace import Workspace

    data = metrics.project_metrics(db, project.id)
    events = repo.events_since(db, project.id)
    phases = [e.message for e in events if e.kind == "phase_started"]
    releases = [e.payload.get("version") for e in events if e.kind == "release_created"]
    fallbacks = sum(1 for e in events if e.kind == "llm_replay_fallback")
    drifts = sum(1 for e in events if e.kind == "llm_replay_drift")
    print("\n=== Summary ===")
    print(f"Phases:    {' > '.join(phases)}")
    print(f"Releases:  {', '.join(releases) or 'none'}")
    print(f"Bugs:      {db.query(m.Bug).count()} reported, "
          f"{db.query(m.Bug).filter_by(status='open').count()} open at the end")
    print(f"Modes:     {', '.join(data['project']['llm_modes']) or 'none'}"
          f" ({fallbacks} mock fallbacks, {drifts} prompt drifts)")
    print(f"Workspace: {Workspace(project.id).path}")
    print("\nSprint  Committed  Completed  Reliability  First-pass  Bugs  Process")
    for s in data["sprints"]:
        p = s["process"]
        print(f"{s['sprint_number']:>6}  {s['committed_points']:>9}  {s['completed_points']:>9}  "
              f"{_pct(s['commitment_reliability']):>11}  {_pct(s['first_pass_yield']):>10}  "
              f"{s['bugs_reported']:>4}  capacity {p.get('capacity')}, retries "
              f"{p.get('max_fix_retries')}, test-first {'on' if p.get('test_first') else 'off'}")
    print("\nImprovement (Plan-Do-Check-Act):")
    for row in metrics.improvement_rows(db, project.id):
        deltas = {k: v for k, v in row["deltas"].items() if v is not None}
        changes = row["act"]["proposed_changes"]
        proposed = {k: v for k, v in changes.items() if v not in (None, [], "") and k != "reason"}
        print(f"  Sprint {row['sprint_number']}: committed {row['do']['committed_points']}, "
              f"completed {row['do']['completed_points']}; change vs previous: "
              f"{deltas or 'n/a'}; next process: {proposed or 'unchanged'}")


def _pct(value) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def cmd_run(args) -> int:
    scenario = configure(args.scenario, args.mode, args.fresh)
    from workbench.llm.client import LLMError

    db, project = open_project(scenario, args.fresh)
    if project.phase == "done":
        print("This run is already finished; use --fresh to run it again.")
        print_summary(db, project)
        return 0
    reset_replay()
    print(f"Scenario '{args.scenario}' in {args.mode} mode "
          f"(database {os.environ['DATABASE_URL']})")
    try:
        run_project(db, project, args.step)
    except LLMError as exc:
        print(f"\nStopped: {exc}", file=sys.stderr)
        return 2
    print_summary(db, project)
    return 0


# --- serve --------------------------------------------------------------------------------------


def cmd_serve(args) -> int:
    scenario = configure(args.scenario, args.mode, args.fresh)
    db, project = open_project(scenario, args.fresh)
    reset_replay()
    print(f"Scenario '{args.scenario}' ({args.mode}): project {project.id} "
          f"'{project.name}', phase '{project.phase}'.")
    print(f"Open the UI:  cd frontend && npm run dev   then http://localhost:5173/projects/"
          f"{project.id}")
    print(f"API docs:     http://{args.host}:{args.port}/docs")
    db.close()
    import uvicorn

    uvicorn.run("workbench.api.main:app", host=args.host, port=args.port, log_level="warning")
    return 0


# --- record -------------------------------------------------------------------------------------


def cmd_record(args) -> int:
    from dotenv import load_dotenv

    os.chdir(ROOT)
    load_dotenv()
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set (put it in .env). Recording calls the real model.",
              file=sys.stderr)
        return 1
    print("WARNING: recording calls the real model for every agent step and costs money:")
    print("a full three-sprint run is several dozen calls (tens of thousands of tokens each).")
    if input("Type 'yes' to continue: ").strip().lower() != "yes":
        print("Cancelled.")
        return 1
    args.mode, args.step = "record", False
    folder, scenario = load_scenario(args.scenario)
    target = SCENARIOS / f"{args.scenario}-recorded"
    target.mkdir(parents=True, exist_ok=True)
    recorded = {**scenario, "name": f"{args.scenario}-recorded", "source": "recorded",
                "fallback": "error"}
    (target / "scenario.json").write_text(json.dumps(recorded, indent=2) + "\n", encoding="utf-8")
    code = cmd_run(args)
    print(f"Recorded calls: {target / 'calls'}  (replay with --scenario {args.scenario}-recorded)")
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p, mode_default="replay"):
        p.add_argument("--scenario", required=True, help="name under demo/scenarios")
        p.add_argument("--fresh", action="store_true", help="delete the run database first")
        p.add_argument("--mode", choices=MODES, default=mode_default)

    run = sub.add_parser("run", help="run a scenario from idea to done")
    common(run)
    run.add_argument("--step", action="store_true", help="pause after every phase")
    run.set_defaults(func=cmd_run)

    serve = sub.add_parser("serve", help="serve the API for the UI with a fresh scenario project")
    common(serve)
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--host", default="127.0.0.1")
    serve.set_defaults(func=cmd_serve)

    record = sub.add_parser("record", help="run against the real model and save the answers")
    record.add_argument("--scenario", required=True)
    record.add_argument("--fresh", action="store_true", default=True)
    record.set_defaults(func=cmd_record)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
