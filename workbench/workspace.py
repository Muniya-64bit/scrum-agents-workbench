"""Per-project sandbox workspace: a plain directory with its own git repository.

Agents that produce code (Developer, later QA and DevOps) write files here and commit them, so
the generated app has a real history with one commit per story. Paths from the LLM are checked so
nothing is written outside the workspace or into `.git`."""

import subprocess
from pathlib import Path, PurePosixPath

from workbench import config

GIT_AUTHOR = ["-c", "user.name=Workbench Agent", "-c", "user.email=agent@workbench.local",
              "-c", "commit.gpgsign=false"]


class UnsafePath(ValueError):
    pass


class Workspace:
    def __init__(self, project_id: int, root: str | Path | None = None):
        base = Path(root if root is not None else config.WORKSPACES_DIR).resolve()
        self.path = base / f"project-{project_id}"

    def init(self) -> "Workspace":
        """Create the directory and its git repository if they do not exist yet."""
        if not (self.path / ".git").exists():
            self.path.mkdir(parents=True, exist_ok=True)
            self._git("init", "-q")
        return self

    def resolve(self, rel: str) -> Path:
        """Map a workspace-relative path to a real path, rejecting anything that escapes."""
        p = PurePosixPath(rel.replace("\\", "/"))
        if not rel.strip() or p.is_absolute() or ":" in p.parts[0] or ".." in p.parts \
                or ".git" in p.parts:
            raise UnsafePath(f"unsafe path: {rel!r}")
        return self.path.joinpath(*p.parts)

    def write(self, rel: str, content: str) -> bool:
        """Write a file. Returns False when the content is unchanged."""
        target = self.resolve(rel)
        if target.is_file() and target.read_text(encoding="utf-8") == content:
            return False
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="")
        return True

    def read(self, rel: str) -> str:
        return self.resolve(rel).read_text(encoding="utf-8")

    def files(self) -> list[str]:
        """All files in the workspace (posix paths), excluding `.git`."""
        if not self.path.exists():
            return []
        return sorted(p.relative_to(self.path).as_posix() for p in self.path.rglob("*")
                      if p.is_file() and ".git" not in p.relative_to(self.path).parts)

    def commit(self, message: str) -> str | None:
        """Stage everything and commit. Returns the commit sha, or None if nothing changed."""
        self._git("add", "-A")
        if not self._git("status", "--porcelain"):
            return None
        self._git(*GIT_AUTHOR, "commit", "-q", "-m", message)
        return self._git("rev-parse", "HEAD")

    def head(self) -> str | None:
        """The sha of the current commit, or None when there is no commit yet."""
        if not (self.path / ".git").exists():
            return None
        try:
            return self._git("rev-parse", "HEAD")
        except subprocess.CalledProcessError:
            return None

    def _tag_sha(self, name: str) -> str | None:
        try:
            return self._git("rev-parse", "--verify", "-q", f"{name}^{{commit}}")
        except subprocess.CalledProcessError:
            return None

    def tag(self, name: str, message: str = "") -> str:
        """Create an annotated tag on HEAD and return the sha it points to. An existing tag is
        left alone (its sha is returned), so tagging a release twice is harmless."""
        existing = self._tag_sha(name)
        if existing:
            return existing
        self._git(*GIT_AUTHOR, "-c", "tag.gpgsign=false", "tag", "-a", name, "-m",
                  message or name)
        return self._tag_sha(name) or ""

    def log_since(self, tag: str | None) -> list[str]:
        """Commit subjects after `tag`, newest first. No tag, or an unknown one: all commits."""
        if not (self.path / ".git").exists():
            return []
        args = ["log", "--format=%s"]
        if tag and self._tag_sha(tag):
            args.append(f"{tag}..HEAD")
        try:
            return self._git(*args).splitlines()
        except subprocess.CalledProcessError:  # no commits yet
            return []

    def history(self) -> list[str]:
        """Commit subjects, newest first."""
        if not (self.path / ".git").exists():
            return []
        try:
            out = self._git("log", "--format=%s")
        except subprocess.CalledProcessError:  # no commits yet
            return []
        return out.splitlines()

    def _git(self, *args: str) -> str:
        r = subprocess.run(["git", *args], cwd=self.path, capture_output=True, text=True,
                           check=True)
        return r.stdout.strip()
