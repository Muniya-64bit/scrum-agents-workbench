import subprocess

import pytest

from workbench.workspace import Workspace


@pytest.fixture
def ws(tmp_path) -> Workspace:
    return Workspace(1, tmp_path).init()


def commit(ws: Workspace, name: str) -> str:
    ws.write(f"{name}.txt", name)
    return ws.commit(f"Add {name}")


def tags(ws: Workspace) -> list[str]:
    out = subprocess.run(["git", "tag", "--list"], cwd=ws.path, capture_output=True, text=True)
    return out.stdout.split()


def test_head_is_none_without_commits(ws: Workspace, tmp_path):
    assert ws.head() is None
    assert Workspace(2, tmp_path).head() is None  # not even initialised


def test_head_is_the_latest_commit(ws: Workspace):
    first = commit(ws, "a")
    assert ws.head() == first
    assert commit(ws, "b") == ws.head() != first


def test_tag_creates_an_annotated_tag(ws: Workspace):
    sha = commit(ws, "a")
    assert ws.tag("v0.1.0", "Release v0.1.0") == sha
    assert tags(ws) == ["v0.1.0"]
    kind = subprocess.run(["git", "cat-file", "-t", "v0.1.0"], cwd=ws.path, capture_output=True,
                          text=True).stdout.strip()
    assert kind == "tag"  # annotated, not lightweight


def test_tag_is_idempotent(ws: Workspace):
    first = commit(ws, "a")
    ws.tag("v0.1.0")
    commit(ws, "b")
    assert ws.tag("v0.1.0") == first  # the existing tag is left where it was
    assert tags(ws) == ["v0.1.0"]


def test_log_since_lists_commits_after_the_tag(ws: Workspace):
    commit(ws, "a")
    ws.tag("v0.1.0")
    commit(ws, "b")
    commit(ws, "c")
    assert ws.log_since("v0.1.0") == ["Add c", "Add b"]


def test_log_since_without_a_tag_lists_everything(ws: Workspace):
    commit(ws, "a")
    commit(ws, "b")
    assert ws.log_since(None) == ["Add b", "Add a"]
    assert ws.log_since("v9.9.9") == ["Add b", "Add a"]  # unknown tag


def test_log_since_on_an_empty_repository(ws: Workspace, tmp_path):
    assert ws.log_since(None) == []
    assert Workspace(2, tmp_path).log_since(None) == []
