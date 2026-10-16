"""Run the generated project's tests in its workspace and parse the outcome.

The tests are LLM-written code, so they run in a subprocess with a time limit, in the workspace
directory, and without the API key in their environment. This is a plain directory, not a
container: it limits accidents, not a hostile program."""

import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

TIMEOUT_SECONDS = 120
MAX_MESSAGE_CHARS = 400


@dataclass
class Failure:
    test: str
    message: str


@dataclass
class TestResult:
    __test__ = False  # not a pytest test class, despite the name

    passed: int = 0
    failures: list[Failure] = field(default_factory=list)
    output: str = ""

    @property
    def ok(self) -> bool:
        return not self.failures and self.passed > 0


def run_pytest(workspace: Path, targets: Sequence[str] = ("tests",),
               timeout: int = TIMEOUT_SECONDS) -> TestResult:
    """Run pytest on `targets` inside `workspace`. Never raises on test failures."""
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"  # no __pycache__ in the workspace (it is a git repo)
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "report.xml"
        cmd = [sys.executable, "-m", "pytest", *targets, "-q", "--tb=short", "-p",
               "no:cacheprovider", f"--junitxml={report}"]
        try:
            r = subprocess.run(cmd, cwd=workspace, capture_output=True, text=True, env=env,
                               timeout=timeout)
        except subprocess.TimeoutExpired:
            return TestResult(failures=[Failure("timeout", f"Tests timed out after {timeout}s")])
        output = (r.stdout + r.stderr)[-2000:]
        if not report.exists():  # pytest crashed before writing a report
            return TestResult(failures=[Failure("pytest", output[-MAX_MESSAGE_CHARS:])],
                              output=output)
        return _parse(report, output, r.returncode)


def _parse(report: Path, output: str, returncode: int) -> TestResult:
    result = TestResult(output=output)
    for case in ET.parse(report).getroot().iter("testcase"):
        name = f"{case.get('classname', '')}.{case.get('name', '')}".strip(".")
        problem = case.find("failure")
        if problem is None:
            problem = case.find("error")
        if problem is not None:
            text = (problem.get("message") or problem.text or "").strip().splitlines()
            result.failures.append(Failure(name, " ".join(text)[:MAX_MESSAGE_CHARS]))
        elif case.find("skipped") is None:
            result.passed += 1
    if returncode == 5 or (not result.failures and result.passed == 0):  # nothing collected
        result.failures.append(Failure("collection", "No tests were collected"))
    return result
