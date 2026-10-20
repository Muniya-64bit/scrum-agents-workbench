"""Static check of model-written files: undefined names and syntax errors."""

from workbench import staticcheck


def test_a_clean_file_has_no_problems():
    assert staticcheck.problems("app/main.py", "import os\n\nx = os.sep\n") == []


def test_an_undefined_name_is_reported_with_its_line():
    source = "def f():\n    return Path('x')\n"
    assert staticcheck.problems("app/main.py", source) == [
        "app/main.py line 2: Undefined name `Path` -- the line is: return Path('x')"]


def test_a_syntax_error_is_reported():
    (problem,) = staticcheck.problems("app/main.py", "def f(a=1, b):\n    pass\n")
    assert problem.startswith("app/main.py line 1:") and "without a default" in problem
    assert problem.endswith("-- the line is: def f(a=1, b):")


def test_the_offending_line_is_shown_so_the_model_can_see_what_to_fix():
    """A live model was refused 23 times for 'simple statements must be separated by newlines'
    without being shown the line."""
    (problem,) = staticcheck.problems("app/main.py", "init_db() app = FastAPI()\n")
    assert "-- the line is: init_db() app = FastAPI()" in problem


def test_unused_imports_are_not_a_problem():
    assert staticcheck.problems("app/main.py", "import os\nimport json\n") == []


def test_at_most_five_problems_are_listed():
    source = "".join(f"x{i} = missing{i}\n" for i in range(9))
    assert len(staticcheck.problems("app/main.py", source)) == staticcheck.MAX_PROBLEMS


def test_a_missing_ruff_skips_the_check(monkeypatch):
    class Gone:
        returncode, stdout, stderr = 1, "", "/usr/bin/python: No module named ruff"

    monkeypatch.setattr(staticcheck.subprocess, "run", lambda *a, **k: Gone())
    assert staticcheck.problems("app/main.py", "x = missing\n") == []


def test_a_timeout_skips_the_check(monkeypatch):
    def slow(*args, **kwargs):
        raise staticcheck.subprocess.TimeoutExpired("ruff", 1)

    monkeypatch.setattr(staticcheck.subprocess, "run", slow)
    assert staticcheck.problems("app/main.py", "x = missing\n") == []
