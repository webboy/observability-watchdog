"""SQLAlchemy engine, session factory, and FastAPI dependency."""

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    """Yield a database session for request-scoped use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database_connection() -> bool:
    """Return True when the database accepts a simple query."""
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return True
