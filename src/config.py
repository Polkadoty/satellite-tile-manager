"""Application configuration."""

import os
from pathlib import Path
from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Environment
    environment: str = "development"  # development, production, vercel

    # Database - supports SQLite, PostgreSQL, and Vercel Postgres
    database_url: str = "sqlite:///./data/tiles.db"

    # Storage - local or cloud (Vercel Blob)
    tiles_dir: Path = Path("./data/tiles")
    cache_dir: Path = Path("./data/cache")

    # Vercel Blob Storage (optional, for serverless)
    blob_read_write_token: str = ""  # BLOB_READ_WRITE_TOKEN from Vercel

    # API Keys for tile providers
    google_maps_api_key: str = ""
    bing_maps_api_key: str = ""
    mapbox_access_token: str = ""

    # NAIP settings (free, no key needed)
    naip_base_url: str = "https://naip-usdaonline.hub.arcgis.com"

    # Tile settings
    default_tile_size: int = 256
    max_zoom_level: int = 20
    default_gsd_meters: float = 0.6  # Ground sampling distance

    # Processing
    max_concurrent_downloads: int = 5
    download_timeout_seconds: int = 30

    # Caching
    cache_max_size_mb: int = 100
    cache_max_entries: int = 1000
    cache_ttl_seconds: int = 3600

    # Coordinate reference systems
    default_crs: str = "EPSG:4326"  # WGS84
    storage_crs: str = "EPSG:4326"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    @property
    def is_serverless(self) -> bool:
        """Check if running in serverless environment."""
        return self.environment == "vercel" or os.environ.get("VERCEL") == "1"

    @property
    def use_blob_storage(self) -> bool:
        """Check if Vercel Blob storage should be used."""
        return bool(self.blob_read_write_token) and self.is_serverless


settings = Settings()
