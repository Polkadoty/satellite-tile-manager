"""ESRI/ArcGIS World Imagery tile provider.

ESRI World Imagery provides high-resolution satellite and aerial imagery
with global coverage. Free tier available for non-commercial use.
"""

from src.db.models import ProviderName
from src.providers.base import TileProvider, TileResult


class ESRIProvider(TileProvider):
    """ESRI World Imagery tile provider.

    Uses ArcGIS Online World Imagery basemap which provides
    high-resolution satellite imagery globally.
    """

    name = ProviderName.ESRI
    display_name = "ESRI World Imagery"
    max_zoom = 23  # ESRI supports very high zoom in some areas
    requires_api_key = False  # Free tier available

    # ESRI World Imagery tile service
    BASE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile"

    def get_tile_url(self, x: int, y: int, zoom: int) -> str:
        """Get ESRI tile URL using ArcGIS REST tile scheme.

        Note: ESRI uses TMS-style URLs: {zoom}/{y}/{x}
        """
        return f"{self.BASE_URL}/{zoom}/{y}/{x}"

    async def get_tile(self, x: int, y: int, zoom: int) -> TileResult:
        """Download an ESRI World Imagery tile."""
        bounds = self.tile_to_bounds(x, y, zoom)
        min_lon, min_lat, max_lon, max_lat = bounds
        center_lat = (min_lat + max_lat) / 2

        gsd = self.calculate_gsd(center_lat, zoom)
        save_path = self.get_storage_path(x, y, zoom, "jpg")

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
            file_format="jpg",
            min_lon=min_lon,
            min_lat=min_lat,
            max_lon=max_lon,
            max_lat=max_lat,
            gsd=gsd,
            metadata={
                "source": "ESRI World Imagery",
                "coverage": "Global",
                "attribution": "Esri, Maxar, Earthstar Geographics, and the GIS User Community",
            },
            error=error,
        )


class ESRIWMSProvider(TileProvider):
    """Alternative ESRI provider using WMS for more flexibility.

    Useful when you need specific export parameters or formats.
    """

    name = ProviderName.ESRI
    display_name = "ESRI WMS"
    max_zoom = 20
    requires_api_key = False

    # ESRI Export endpoint for custom bbox requests
    BASE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export"

    def get_tile_url(self, x: int, y: int, zoom: int) -> str:
        """Get ESRI export URL with bbox."""
        bounds = self.tile_to_bounds(x, y, zoom)
        min_lon, min_lat, max_lon, max_lat = bounds

        url = (
            f"{self.BASE_URL}?"
            f"bbox={min_lon},{min_lat},{max_lon},{max_lat}"
            f"&bboxSR=4326"
            f"&imageSR=4326"
            f"&size={self.tile_size},{self.tile_size}"
            f"&format=png"
            f"&f=image"
        )
        return url

    async def get_tile(self, x: int, y: int, zoom: int) -> TileResult:
        """Download an ESRI tile via export endpoint."""
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
            metadata={
                "source": "ESRI World Imagery (Export)",
                "coverage": "Global",
            },
            error=error,
        )


class ESRIClarityProvider(TileProvider):
    """ESRI Clarity (enhanced) satellite imagery.

    Provides sharper, enhanced imagery in supported areas.
    """

    name = ProviderName.ESRI
    display_name = "ESRI Clarity"
    max_zoom = 20
    requires_api_key = False

    # ESRI Clarity tile service
    BASE_URL = "https://clarity.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/MapServer/tile"

    def get_tile_url(self, x: int, y: int, zoom: int) -> str:
        """Get ESRI Clarity tile URL."""
        return f"{self.BASE_URL}/{zoom}/{y}/{x}"

    async def get_tile(self, x: int, y: int, zoom: int) -> TileResult:
        """Download an ESRI Clarity tile."""
        bounds = self.tile_to_bounds(x, y, zoom)
        min_lon, min_lat, max_lon, max_lat = bounds
        center_lat = (min_lat + max_lat) / 2

        gsd = self.calculate_gsd(center_lat, zoom)
        save_path = self.get_storage_path(x, y, zoom, "jpg")

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
            file_format="jpg",
            min_lon=min_lon,
            min_lat=min_lat,
            max_lon=max_lon,
            max_lat=max_lat,
            gsd=gsd,
            metadata={
                "source": "ESRI Clarity Enhanced Imagery",
                "coverage": "Selected urban areas",
            },
            error=error,
        )
