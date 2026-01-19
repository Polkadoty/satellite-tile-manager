"""Database base configuration."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.config import settings


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


def get_sync_engine():
    """Get synchronous database engine."""
    url = settings.database_url
    connect_args = {}

    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        # Enable spatialite for SQLite
        engine = create_engine(url, connect_args=connect_args, echo=settings.debug)

        @event.listens_for(engine, "connect")
        def load_spatialite(dbapi_conn, connection_record):
            dbapi_conn.enable_load_extension(True)
            try:
                dbapi_conn.load_extension("mod_spatialite")
            except Exception:
                # SpatiaLite not available, geometry will be stored as text
                pass
            dbapi_conn.enable_load_extension(False)

        return engine

    return create_engine(url, echo=settings.debug)


def get_async_engine():
    """Get async database engine."""
    url = settings.database_url

    # Convert to async URL
    if url.startswith("sqlite"):
        async_url = url.replace("sqlite://", "sqlite+aiosqlite://")
    elif url.startswith("postgresql"):
        async_url = url.replace("postgresql://", "postgresql+asyncpg://")
    else:
        async_url = url

    return create_async_engine(async_url, echo=settings.debug)


# Synchronous session factory
sync_engine = get_sync_engine()
SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)


def get_db() -> Session:
    """Get synchronous database session."""
    db = SyncSessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=sync_engine)
    # Ensure storage directories exist
    settings.tiles_dir.mkdir(parents=True, exist_ok=True)
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
