"""Checks on a release: does the app start, does it serve its contract, is it fast enough, is it
free of common security mistakes.

QA tests the stories one by one; these checks look at the whole generated app, the way a deployment
would. They run when a sprint is released and are reported with the release (an event for each
check, a section of the release notes, the Results page). Nothing here blocks a release: a failed
check is a finding, not a veto."""

import json
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from workbench import contract, staticcheck
from workbench.contract import Endpoint

START_SECONDS = 20  # how long the app may take to start answering
REQUEST_SECONDS = 5
LATENCY_SAMPLES = 10  # requests per list endpoint, to take a p95
_MS = re.compile(r"(\d+(?:\.\d+)?)\s*ms", re.IGNORECASE)
_LATENCY_WORDS = re.compile(r"respon|latenc|answer|request|time", re.IGNORECASE)


@dataclass
class Check:
    name: str
    status: str  # passed | failed | skipped | met | not met | unverified
    detail: str = ""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get(url: str) -> tuple[int, float]:
    """(status, seconds) of one GET; an HTTP error still has a status, a refused one is 0."""
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=REQUEST_SECONDS) as r:
            r.read()
            return r.status, time.perf_counter() - started
    except urllib.error.HTTPError as e:
        return e.code, time.perf_counter() - started
    except (OSError, ValueError):
        return 0, time.perf_counter() - started


def _norm(path: str) -> str:
    return re.sub(r"\{[^}]*\}", "{}", path.rstrip("/") or "/")


def _p95(seconds: list[float]) -> float:
    ordered = sorted(seconds)
    return ordered[max(0, int(len(ordered) * 0.95) - 1)] * 1000


def smoke_test(workspace: Path, endpoints: list[Endpoint]) -> tuple[list[Check], float | None]:
    """Start `app.main:app` in the workspace, read its OpenAPI document, compare it with the
    contract and time its list endpoints. Returns the checks and the p95 latency in ms (None when
    the app did not start or has no list endpoint)."""
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port),
         "--host", "127.0.0.1"], cwd=workspace, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True)
    try:
        deadline = time.monotonic() + START_SECONDS
        status = 0
        while time.monotonic() < deadline and proc.poll() is None:
            status, _ = _get(f"{base}/openapi.json")
            if status == 200:
                break
            time.sleep(0.3)
        if status != 200:
            tail = ""
            if proc.poll() is not None and proc.stderr:
                tail = " ".join(proc.stderr.read().strip().splitlines()[-2:])[:200]
            return [Check("starts", "failed", tail or "the app did not answer in time")], None
        checks = [Check("starts", "passed", "serves its OpenAPI document")]
        with urllib.request.urlopen(f"{base}/openapi.json", timeout=REQUEST_SECONDS) as r:
            paths = json.load(r).get("paths", {})
        checks.append(_contract_check(paths, endpoints))
        samples = []
        for path, methods in paths.items():
            if "get" in methods and "{" not in path:
                samples += [_get(base + path)[1] for _ in range(LATENCY_SAMPLES)]
        return checks, (_p95(samples) if samples else None)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


def _contract_check(paths: dict, endpoints: list[Endpoint]) -> Check:
    if not endpoints:
        return Check("serves its contract", "skipped", "no completed story has a contract")
    served = [Endpoint(m.upper(), _norm(p)) for p, methods in paths.items() for m in methods]
    wanted = [Endpoint(e.method, _norm(e.path), e.success_status) for e in endpoints]
    missing = [str(e) for e in contract.lost(wanted, served)]
    if missing:
        return Check("serves its contract", "failed", "not served: " + ", ".join(missing))
    return Check("serves its contract", "passed", f"all {len(endpoints)} endpoints are served")


def check_nfrs(nfrs: list[dict], p95_ms: float | None) -> list[Check]:
    """Verify the non-functional requirements that name a time in milliseconds against the
    measured p95; every other requirement is reported as not verified (no automatic check)."""
    results = []
    for n in nfrs:
        text = f"{n.get('requirement', '')} {n.get('measure', '')}"
        limit = _MS.search(text)
        name = (n.get("requirement") or "requirement")[:90]
        if limit and _LATENCY_WORDS.search(text) and p95_ms is not None:
            status = "met" if p95_ms <= float(limit.group(1)) else "not met"
            results.append(Check(name, status, f"p95 {p95_ms:.0f} ms against {limit.group(1)} ms"))
        else:
            results.append(Check(name, "unverified", "no automatic check for this requirement"))
    return results


def security_scan(workspace: Path) -> list[str]:
    """Security findings of every `app/*.py` file."""
    findings = []
    for path in sorted((workspace / "app").rglob("*.py")) if (workspace / "app").is_dir() else []:
        rel = path.relative_to(workspace).as_posix()
        findings += staticcheck.security_findings(rel, path.read_text(encoding="utf-8"))
    return findings
