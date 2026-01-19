"""Application configuration."""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "sqlite:///./data/tiles.db"

    # Storage
    tiles_dir: Path = Path("./data/tiles")
    cache_dir: Path = Path("./data/cache")

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

    # Coordinate reference systems
    default_crs: str = "EPSG:4326"  # WGS84
    storage_crs: str = "EPSG:4326"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False


settings = Settings()
