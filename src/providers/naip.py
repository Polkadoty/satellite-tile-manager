"""NAIP (National Agriculture Imagery Program) tile provider.

NAIP provides free, high-resolution aerial imagery of the continental US.
Resolution is typically 0.6m-1m per pixel, updated every 2 years.
"""

from src.config import settings
from src.db.models import ProviderName
from src.providers.base import TileProvider, TileResult


class NAIPProvider(TileProvider):
    """NAIP tile provider using USDA's ArcGIS REST API."""

    name = ProviderName.NAIP
    display_name = "NAIP (USDA)"
    max_zoom = 18  # NAIP max zoom is typically 18
    requires_api_key = False

    # NAIP imagery service endpoint
    BASE_URL = "https://gis.apfo.usda.gov/arcgis/rest/services/NAIP/USDA_CONUS_PRIME/ImageServer"

    def get_tile_url(self, x: int, y: int, zoom: int) -> str:
        """Get NAIP tile URL using ArcGIS export endpoint."""
        bounds = self.tile_to_bounds(x, y, zoom)
        min_lon, min_lat, max_lon, max_lat = bounds

        # Use the export endpoint with bbox
        # NAIP uses EPSG:4326 for geographic coordinates
        url = (
            f"{self.BASE_URL}/exportImage?"
            f"bbox={min_lon},{min_lat},{max_lon},{max_lat}"
            f"&bboxSR=4326"
            f"&imageSR=4326"
            f"&size={self.tile_size},{self.tile_size}"
            f"&format=tiff"
            f"&f=image"
        )
        return url

    async def get_tile(self, x: int, y: int, zoom: int) -> TileResult:
        """Download a NAIP tile."""
        bounds = self.tile_to_bounds(x, y, zoom)
        min_lon, min_lat, max_lon, max_lat = bounds
        center_lat = (min_lat + max_lat) / 2

        gsd = self.calculate_gsd(center_lat, zoom)
        save_path = self.get_storage_path(x, y, zoom, "tif")

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
            file_format="tif",
            min_lon=min_lon,
            min_lat=min_lat,
            max_lon=max_lon,
            max_lat=max_lat,
            gsd=gsd,
            metadata={"source": "USDA NAIP", "coverage": "Continental US"},
            error=error,
        )


class NAIPWMSProvider(TileProvider):
    """Alternative NAIP provider using WMS endpoint for more flexibility."""

    name = ProviderName.NAIP
    display_name = "NAIP WMS"
    max_zoom = 18
    requires_api_key = False

    # Alternative WMS endpoint
    WMS_URL = "https://gis.apfo.usda.gov/arcgis/services/NAIP/USDA_CONUS_PRIME/ImageServer/WMSServer"

    def get_tile_url(self, x: int, y: int, zoom: int) -> str:
        """Get NAIP tile URL using WMS GetMap."""
        bounds = self.tile_to_bounds(x, y, zoom)
        min_lon, min_lat, max_lon, max_lat = bounds

        url = (
            f"{self.WMS_URL}?"
            f"SERVICE=WMS"
            f"&VERSION=1.3.0"
            f"&REQUEST=GetMap"
            f"&LAYERS=0"
            f"&STYLES="
            f"&CRS=EPSG:4326"
            f"&BBOX={min_lat},{min_lon},{max_lat},{max_lon}"
            f"&WIDTH={self.tile_size}"
            f"&HEIGHT={self.tile_size}"
            f"&FORMAT=image/tiff"
        )
        return url

    async def get_tile(self, x: int, y: int, zoom: int) -> TileResult:
        """Download a NAIP tile via WMS."""
        bounds = self.tile_to_bounds(x, y, zoom)
        min_lon, min_lat, max_lon, max_lat = bounds
        center_lat = (min_lat + max_lat) / 2

        gsd = self.calculate_gsd(center_lat, zoom)
        save_path = self.get_storage_path(x, y, zoom, "tif")

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
            file_format="tif",
            min_lon=min_lon,
            min_lat=min_lat,
            max_lon=max_lon,
            max_lat=max_lat,
            gsd=gsd,
            metadata={"source": "USDA NAIP WMS", "coverage": "Continental US"},
            error=error,
        )
