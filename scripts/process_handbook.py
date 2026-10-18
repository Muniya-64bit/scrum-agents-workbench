"""Regenerate the tables in docs/process-handbook.md from the process model.

    python scripts/process_handbook.py           # rewrite the generated part
    python scripts/process_handbook.py --check   # exit 1 if the handbook is out of date

Only the text between the `generated:start` and `generated:end` markers is replaced; the rest of
the handbook is written by hand. The model is `workbench/process_model.py`."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workbench.process_model import handbook_tables  # noqa: E402

HANDBOOK = ROOT / "docs" / "process-handbook.md"
START, END = "<!-- generated:start -->", "<!-- generated:end -->"


def render(text: str) -> str:
    head, rest = text.split(START, 1)
    tail = rest.split(END, 1)[1]
    return f"{head}{START}\n{handbook_tables()}{END}{tail}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="only report whether it is current")
    args = parser.parse_args()
    text = HANDBOOK.read_text(encoding="utf-8")
    new = render(text)
    if args.check:
        print("up to date" if new == text else "out of date")
        return 0 if new == text else 1
    HANDBOOK.write_text(new, encoding="utf-8", newline="\n")
    print(f"wrote {HANDBOOK.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
