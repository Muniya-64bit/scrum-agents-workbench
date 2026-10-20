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


def test_a_nul_character_is_a_syntax_problem_even_without_ruff(monkeypatch):
    """A live run wrote NUL bytes into app/main.py; the compiler refuses such a file."""
    monkeypatch.setattr(staticcheck.subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("no ruff")))
    (problem,) = staticcheck.problems("app/main.py", "x = 1\x00\n")
    assert problem.startswith("app/main.py") and "null bytes" in problem


def test_syntax_problem_names_the_line_and_is_none_for_good_code():
    assert staticcheck.syntax_problem("app/main.py", "x = 1\n") is None
    found = staticcheck.syntax_problem("app/main.py", "x = 1\nif x = 2:\n    pass\n")
    assert found.startswith("app/main.py line 2:") and "-- the line is: if x = 2:" in found


def test_ruff_failing_to_run_does_not_hide_a_compile_error(monkeypatch):
    class Broken:
        returncode, stdout, stderr = 2, "", "ruff could not read the input"

    monkeypatch.setattr(staticcheck.subprocess, "run", lambda *a, **k: Broken())
    assert staticcheck.problems("app/main.py", "def f(:\n") != []  # the compiler still decides
    assert staticcheck.problems("app/main.py", "x = missing\n") == []  # ruff's part is skipped
