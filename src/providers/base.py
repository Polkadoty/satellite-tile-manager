"""Base class for tile providers."""

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

from src.config import settings
from src.db.models import ProviderName


@dataclass
class TileResult:
    """Result of a tile download operation."""

    success: bool
    tile_x: int
    tile_y: int
    zoom: int
    provider: ProviderName

    # File info (if successful)
    file_path: Optional[Path] = None
    file_size: Optional[int] = None
    file_format: str = "png"

    # Geographic bounds
    min_lat: float = 0.0
    max_lat: float = 0.0
    min_lon: float = 0.0
    max_lon: float = 0.0
    gsd: float = 0.0  # Ground sampling distance

    # Metadata
    capture_date: Optional[datetime] = None
    metadata: dict = field(default_factory=dict)

    # Error info (if failed)
    error: Optional[str] = None


class TileProvider(ABC):
    """Abstract base class for satellite tile providers."""

    name: ProviderName
    display_name: str
    max_zoom: int = 20
    tile_size: int = 256
    requires_api_key: bool = False

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=settings.download_timeout_seconds)

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    @abstractmethod
    async def get_tile(self, x: int, y: int, zoom: int) -> TileResult:
        """Download a single tile.

        Args:
            x: Tile X coordinate
            y: Tile Y coordinate
            zoom: Zoom level

        Returns:
            TileResult with download status and metadata
        """
        pass

    @abstractmethod
    def get_tile_url(self, x: int, y: int, zoom: int) -> str:
        """Get the URL for a specific tile.

        Args:
            x: Tile X coordinate
            y: Tile Y coordinate
            zoom: Zoom level

        Returns:
            URL string for the tile
        """
        pass

    def tile_to_bounds(self, x: int, y: int, zoom: int) -> tuple[float, float, float, float]:
        """Convert tile coordinates to geographic bounds (WGS84).

        Uses Web Mercator (EPSG:3857) tile scheme.

        Args:
            x: Tile X coordinate
            y: Tile Y coordinate
            zoom: Zoom level

        Returns:
            Tuple of (min_lon, min_lat, max_lon, max_lat)
        """
        n = 2.0**zoom

        # Northwest corner
        lon1 = x / n * 360.0 - 180.0
        lat1_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
        lat1 = math.degrees(lat1_rad)

        # Southeast corner
        lon2 = (x + 1) / n * 360.0 - 180.0
        lat2_rad = math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n)))
        lat2 = math.degrees(lat2_rad)

        return (lon1, lat2, lon2, lat1)  # min_lon, min_lat, max_lon, max_lat

    def bounds_to_tiles(
        self, min_lon: float, min_lat: float, max_lon: float, max_lat: float, zoom: int
    ) -> list[tuple[int, int]]:
        """Convert geographic bounds to tile coordinates.

        Args:
            min_lon: Minimum longitude
            min_lat: Minimum latitude
            max_lon: Maximum longitude
            max_lat: Maximum latitude
            zoom: Zoom level

        Returns:
            List of (x, y) tile coordinates covering the bounds
        """
        min_x, max_y = self.coords_to_tile(min_lon, min_lat, zoom)
        max_x, min_y = self.coords_to_tile(max_lon, max_lat, zoom)

        tiles = []
        for x in range(min_x, max_x + 1):
            for y in range(min_y, max_y + 1):
                tiles.append((x, y))

        return tiles

    def coords_to_tile(self, lon: float, lat: float, zoom: int) -> tuple[int, int]:
        """Convert geographic coordinates to tile coordinates.

        Args:
            lon: Longitude
            lat: Latitude
            zoom: Zoom level

        Returns:
            Tuple of (x, y) tile coordinates
        """
        n = 2.0**zoom
        x = int((lon + 180.0) / 360.0 * n)
        lat_rad = math.radians(lat)
        y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)

        # Clamp to valid range
        x = max(0, min(int(n) - 1, x))
        y = max(0, min(int(n) - 1, y))

        return (x, y)

    def calculate_gsd(self, lat: float, zoom: int) -> float:
        """Calculate ground sampling distance (meters per pixel) at given latitude and zoom.

        Args:
            lat: Latitude in degrees
            zoom: Zoom level

        Returns:
            Ground sampling distance in meters
        """
        # Earth's circumference at equator in meters
        earth_circumference = 40075016.686
        # At zoom 0, the whole world fits in 256 pixels
        # GSD decreases by factor of 2 for each zoom level
        gsd_equator = earth_circumference / (self.tile_size * (2**zoom))
        # Adjust for latitude (Mercator projection)
        gsd = gsd_equator * math.cos(math.radians(lat))
        return gsd

    def get_storage_path(self, x: int, y: int, zoom: int, format: str = "tif") -> Path:
        """Get the storage path for a tile.

        Args:
            x: Tile X coordinate
            y: Tile Y coordinate
            zoom: Zoom level
            format: File format extension

        Returns:
            Path to store the tile
        """
        path = settings.tiles_dir / self.name.value / str(zoom) / str(x)
        path.mkdir(parents=True, exist_ok=True)
        return path / f"{y}.{format}"

    async def download_tile_image(self, url: str, save_path: Path) -> tuple[bool, Optional[str]]:
        """Download tile image from URL and save to disk.

        Args:
            url: URL to download from
            save_path: Path to save the image

        Returns:
            Tuple of (success, error_message)
        """
        try:
            response = await self.client.get(url)
            response.raise_for_status()

            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(response.content)

            return (True, None)
        except httpx.HTTPError as e:
            return (False, f"HTTP error: {e}")
        except Exception as e:
            return (False, f"Download error: {e}")
