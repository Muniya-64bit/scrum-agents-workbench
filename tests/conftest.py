import atexit
import os
import shutil
import tempfile

os.environ["MOCK_LLM"] = "1"
os.environ["LLM_MODE"] = "mock"
# Even code that opens the app's own engine (API lifespan, scripts) must not reach ./workbench.db
_SCRATCH = tempfile.mkdtemp(prefix="workbench-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_SCRATCH}/unused.db"
atexit.register(shutil.rmtree, _SCRATCH, ignore_errors=True)

import pytest  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from workbench.db.session import Base, init_db, make_engine  # noqa: E402


@pytest.fixture
def db():
    engine = make_engine("sqlite://")
    init_db(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as s:
        yield s
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def _workspaces(tmp_path, monkeypatch):
    """Generated code goes to a temp dir, never to ./workspaces."""
    from workbench import config

    monkeypatch.setattr(config, "WORKSPACES_DIR", str(tmp_path / "workspaces"))
