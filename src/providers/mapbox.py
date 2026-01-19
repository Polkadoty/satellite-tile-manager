"""Mapbox satellite tile provider."""

from src.config import settings
from src.db.models import ProviderName
from src.providers.base import TileProvider, TileResult


class MapboxProvider(TileProvider):
    """Mapbox satellite imagery provider.

    Requires a Mapbox access token.
    Uses the Mapbox Static Tiles API.
    """

    name = ProviderName.MAPBOX
    display_name = "Mapbox Satellite"
    max_zoom = 22
    requires_api_key = True

    # Mapbox satellite tile endpoint
    TILES_URL = "https://api.mapbox.com/v4/mapbox.satellite"

    def __init__(self):
        super().__init__()
        self.access_token = settings.mapbox_access_token

    def get_tile_url(self, x: int, y: int, zoom: int) -> str:
        """Get Mapbox satellite tile URL."""
        # Mapbox uses standard XYZ tile scheme
        url = f"{self.TILES_URL}/{zoom}/{x}/{y}@2x.png?access_token={self.access_token}"
        return url

    async def get_tile(self, x: int, y: int, zoom: int) -> TileResult:
        """Download a Mapbox satellite tile."""
        if not self.access_token:
            return TileResult(
                success=False,
                tile_x=x,
                tile_y=y,
                zoom=zoom,
                provider=self.name,
                error="Mapbox access token not configured",
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
            metadata={"source": "Mapbox Satellite", "retina": True},
            error=error,
        )
