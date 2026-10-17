"""List the recorded LLM calls of a scenario and the calls still to author.

    python scripts/scenario_keys.py --scenario demo/scenarios/todo-app
    python scripts/scenario_keys.py --scenario demo/scenarios/todo-app --db demo_runs/todo-app.db

Without --db it prints the call files under <scenario>/calls (key, number, source). With --db it
also prints the keys that a replay run answered from the mock fallback (`llm_replay_fallback`
events): those are the calls you still have to record or write by hand."""

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def recorded_keys(scenario: Path) -> list[tuple[str, int, str]]:
    rows = []
    for path in sorted((scenario / "calls").glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            rows.append((data["key"], int(data["n"]), str(data.get("source", "?"))))
        except (OSError, ValueError, KeyError):
            rows.append((path.stem, 0, "unreadable"))
    return rows


def fallback_keys(db_path: Path) -> list[tuple[str, int]]:
    """Distinct (key, n) of the `llm_replay_fallback` events in a workbench SQLite file."""
    con = sqlite3.connect(str(db_path))
    try:
        found = set()
        for (payload,) in con.execute("select payload from events where kind = ?",
                                      ("llm_replay_fallback",)):
            data = json.loads(payload) if isinstance(payload, str) else payload
            found.add((str(data.get("key", "?")), int(data.get("n", 0))))
        return sorted(found)
    finally:
        con.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scenario", required=True, type=Path, help="scenario directory")
    parser.add_argument("--db", type=Path, help="workbench DB of a replay run (fallback keys)")
    args = parser.parse_args(argv)

    rows = recorded_keys(args.scenario)
    print(f"{len(rows)} call file(s) in {args.scenario / 'calls'}")
    for key, n, source in rows:
        print(f"  {key} #{n}  [{source}]")
    if args.db is not None:
        if not args.db.is_file():
            print(f"No such database: {args.db}", file=sys.stderr)
            return 0
        missing = fallback_keys(args.db)
        print(f"{len(missing)} call(s) still to author (answered by the mock fallback):")
        for key, n in missing:
            print(f"  {key} #{n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
