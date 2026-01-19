"""Bing Maps satellite tile provider."""

from src.config import settings
from src.db.models import ProviderName
from src.providers.base import TileProvider, TileResult


class BingMapsProvider(TileProvider):
    """Bing Maps aerial imagery provider.

    Requires a Bing Maps API key.
    Uses the quadkey tile addressing system.
    """

    name = ProviderName.BING
    display_name = "Bing Maps"
    max_zoom = 21
    requires_api_key = True

    IMAGERY_URL = "https://dev.virtualearth.net/REST/v1/Imagery/Map/Aerial"

    def __init__(self):
        super().__init__()
        self.api_key = settings.bing_maps_api_key

    def tile_to_quadkey(self, x: int, y: int, zoom: int) -> str:
        """Convert tile coordinates to Bing quadkey.

        Bing uses a quadkey system where each zoom level adds one digit.
        """
        quadkey = []
        for i in range(zoom, 0, -1):
            digit = 0
            mask = 1 << (i - 1)
            if (x & mask) != 0:
                digit += 1
            if (y & mask) != 0:
                digit += 2
            quadkey.append(str(digit))
        return "".join(quadkey)

    def get_tile_url(self, x: int, y: int, zoom: int) -> str:
        """Get Bing Maps imagery URL."""
        bounds = self.tile_to_bounds(x, y, zoom)
        min_lon, min_lat, max_lon, max_lat = bounds
        center_lat = (min_lat + max_lat) / 2
        center_lon = (min_lon + max_lon) / 2

        # Use REST API for static imagery
        url = (
            f"{self.IMAGERY_URL}/"
            f"{center_lat},{center_lon}/"
            f"{zoom}?"
            f"mapSize={self.tile_size},{self.tile_size}"
            f"&format=png"
            f"&key={self.api_key}"
        )
        return url

    async def get_tile(self, x: int, y: int, zoom: int) -> TileResult:
        """Download a Bing Maps aerial tile."""
        if not self.api_key:
            return TileResult(
                success=False,
                tile_x=x,
                tile_y=y,
                zoom=zoom,
                provider=self.name,
                error="Bing Maps API key not configured",
            )

        bounds = self.tile_to_bounds(x, y, zoom)
        min_lon, min_lat, max_lon, max_lat = bounds
        center_lat = (min_lat + max_lat) / 2

        gsd = self.calculate_gsd(center_lat, zoom)
        save_path = self.get_storage_path(x, y, zoom, "png")

        url = self.get_tile_url(x, y, zoom)
        success, error = await self.download_tile_image(url, save_path)

        return TileResult(
            success=success,
            tile_x=x,
            tile_y=y,
            zoom=zoom,
            provider=self.name,
            file_path=save_path if success else None,
            file_size=save_path.stat().st_size if success and save_path.exists() else None,
            file_format="png",
            min_lon=min_lon,
            min_lat=min_lat,
            max_lon=max_lon,
            max_lat=max_lat,
            gsd=gsd,
            metadata={"source": "Bing Maps API", "quadkey": self.tile_to_quadkey(x, y, zoom)},
            error=error,
        )
