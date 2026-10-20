"""Catch the cheapest mistakes of a model-written Python file before it is written to disk.

A missing import or a syntax error would otherwise only show up when QA runs the tests, as a
collection error, and cost a whole fix attempt. `ruff` finds them in milliseconds: undefined names
(F821) and syntax errors. It is a dev dependency, so without it the check is skipped."""

import re
import subprocess
import sys

TIMEOUT_SECONDS = 20
MAX_PROBLEMS = 5
_LINE = re.compile(r"^\S+?:(\d+):\d+: (?:F821 |E\d+ )?(.*)$")


def problems(path: str, source: str) -> list[str]:
    """Undefined names and syntax errors of one Python file, as 'line N: message'."""
    cmd = [sys.executable, "-m", "ruff", "check", "--isolated", "--select", "F821,E9",
           "--output-format", "concise", "--stdin-filename", path, "-"]
    try:
        r = subprocess.run(cmd, input=source, capture_output=True, text=True,
                           timeout=TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if r.returncode != 1 or "No module named" in r.stderr:  # clean, or ruff is not installed
        return []
    found = []
    lines = source.splitlines()
    for line in r.stdout.splitlines():
        m = _LINE.match(line)
        if m:
            row = int(m.group(1))
            code = lines[row - 1].strip()[:100] if 0 < row <= len(lines) else ""
            shown = f" -- the line is: {code}" if code else ""
            found.append(f"{path} line {row}: {m.group(2)}{shown}")
    return found[:MAX_PROBLEMS]


# Common security mistakes in generated code (the ruff "S" rules, from bandit): exec and eval,
# hard-coded passwords, pickle, unsafe YAML, weak hashes and SQL built from strings.
SECURITY_RULES = "S102,S105,S106,S107,S301,S307,S324,S506,S608"
_SECURITY_LINE = re.compile(r"^\S+?:(\d+):\d+: (S\d{3}) (.*)$")


def security_findings(path: str, source: str) -> list[str]:
    """Security problems of one Python file, as 'file line N: S608 message'. Not a refusal: the
    findings are reported with the release, because a style rule may be wrong for a given app."""
    cmd = [sys.executable, "-m", "ruff", "check", "--isolated", "--select", SECURITY_RULES,
           "--output-format", "concise", "--stdin-filename", path, "-"]
    try:
        r = subprocess.run(cmd, input=source, capture_output=True, text=True,
                           timeout=TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if r.returncode != 1 or "No module named" in r.stderr:
        return []
    found = []
    for line in r.stdout.splitlines():
        m = _SECURITY_LINE.match(line)
        if m:
            found.append(f"{path} line {m.group(1)}: {m.group(2)} {m.group(3)}")
    return found
