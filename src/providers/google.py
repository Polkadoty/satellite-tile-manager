"""Google Maps satellite tile provider."""

from src.config import settings
from src.db.models import ProviderName
from src.providers.base import TileProvider, TileResult


class GoogleMapsProvider(TileProvider):
    """Google Maps satellite imagery provider.

    Requires a Google Maps API key with Static Maps API enabled.
    Note: Using Google's tile servers directly may violate ToS.
    This implementation uses the official Static Maps API.
    """

    name = ProviderName.GOOGLE
    display_name = "Google Maps"
    max_zoom = 21
    requires_api_key = True

    STATIC_MAPS_URL = "https://maps.googleapis.com/maps/api/staticmap"

    def __init__(self):
        super().__init__()
        self.api_key = settings.google_maps_api_key

    def get_tile_url(self, x: int, y: int, zoom: int) -> str:
        """Get Google Static Maps URL for tile coordinates."""
        bounds = self.tile_to_bounds(x, y, zoom)
        min_lon, min_lat, max_lon, max_lat = bounds
        center_lat = (min_lat + max_lat) / 2
        center_lon = (min_lon + max_lon) / 2

        # Static Maps API uses center point + zoom
        url = (
            f"{self.STATIC_MAPS_URL}?"
            f"center={center_lat},{center_lon}"
            f"&zoom={zoom}"
            f"&size={self.tile_size}x{self.tile_size}"
            f"&maptype=satellite"
            f"&format=png"
            f"&key={self.api_key}"
        )
        return url

    async def get_tile(self, x: int, y: int, zoom: int) -> TileResult:
        """Download a Google Maps satellite tile."""
        if not self.api_key:
            return TileResult(
                success=False,
                tile_x=x,
                tile_y=y,
                zoom=zoom,
                provider=self.name,
                error="Google Maps API key not configured",
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
            metadata={"source": "Google Static Maps API"},
            error=error,
        )
