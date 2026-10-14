import os

os.environ["MOCK_LLM"] = "1"

import pytest
from sqlalchemy.orm import sessionmaker

from workbench.db.session import Base, init_db, make_engine


@pytest.fixture
def db():
    engine = make_engine("sqlite://")
    init_db(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as s:
        yield s
    Base.metadata.drop_all(engine)
