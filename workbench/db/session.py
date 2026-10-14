from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from workbench import config


class Base(DeclarativeBase):
    pass


def make_engine(url: str | None = None):
    url = url or config.DATABASE_URL
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    return create_engine(url, **kwargs)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db(bind=None) -> None:
    from workbench.db import models  # noqa: F401  (register tables)

    Base.metadata.create_all(bind or engine)


def get_session():
    with SessionLocal() as s:
        yield s
