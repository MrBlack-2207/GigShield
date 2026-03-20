# gigshield/backend/app/database.py

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,       # drops stale connections automatically
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


class Base(DeclarativeBase):
    """
    All ORM models inherit from this.
    Import this Base into every file in models/
    and into alembic/env.py for migrations.
    """
    pass


def get_db():
    """
    FastAPI dependency. Use in routers like:
        db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()