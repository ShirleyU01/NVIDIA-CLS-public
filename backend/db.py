from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, declarative_base

from .config import get_settings


Base = declarative_base()


def get_engine():
    settings = get_settings()
    # SQLite URLs are allowed as plain strings; Postgres can be used in env.
    return create_engine(str(settings.database_url), future=True)


engine = get_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables if they do not exist."""
    from . import models  # noqa: F401  # imported for side effects

    Base.metadata.create_all(bind=engine)

