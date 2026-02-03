"""Database base configuration."""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Optional

from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.config import settings


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


def get_database_url() -> str:
    """Get database URL, adjusting for serverless environment."""
    url = settings.database_url

    # On Vercel/serverless, use /tmp for SQLite
    if settings.is_serverless and url.startswith("sqlite"):
        return "sqlite:////tmp/tiles.db"

    return url


def get_sync_engine():
    """Get synchronous database engine."""
    url = get_database_url()
    connect_args = {}

    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        engine = create_engine(url, connect_args=connect_args, echo=settings.debug)

        # Only try to load SpatiaLite if not in serverless (not available there)
        if not settings.is_serverless:
            @event.listens_for(engine, "connect")
            def load_spatialite(dbapi_conn, connection_record):
                try:
                    dbapi_conn.enable_load_extension(True)
                    dbapi_conn.load_extension("mod_spatialite")
                    dbapi_conn.enable_load_extension(False)
                except (AttributeError, Exception):
                    # SpatiaLite or enable_load_extension not available
                    pass

        return engine

    return create_engine(url, echo=settings.debug)


def get_async_engine():
    """Get async database engine."""
    url = get_database_url()

    # Convert to async URL
    if url.startswith("sqlite"):
        async_url = url.replace("sqlite://", "sqlite+aiosqlite://")
    elif url.startswith("postgresql"):
        async_url = url.replace("postgresql://", "postgresql+asyncpg://")
    else:
        async_url = url

    return create_async_engine(async_url, echo=settings.debug)


# Lazy initialization for serverless compatibility
_sync_engine: Optional[object] = None
_session_local: Optional[object] = None


def _get_engine():
    """Get or create the sync engine (lazy initialization)."""
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = get_sync_engine()
    return _sync_engine


def _get_session_factory():
    """Get or create the session factory (lazy initialization)."""
    global _session_local
    if _session_local is None:
        _session_local = sessionmaker(autocommit=False, autoflush=False, bind=_get_engine())
    return _session_local


def get_db() -> Session:
    """Get synchronous database session."""
    SessionLocal = _get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables."""
    engine = _get_engine()
    Base.metadata.create_all(bind=engine)

    # Only create directories in non-serverless environments
    if not settings.is_serverless:
        settings.tiles_dir.mkdir(parents=True, exist_ok=True)
        settings.cache_dir.mkdir(parents=True, exist_ok=True)
