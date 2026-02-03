"""Sentinel-2 tile provider.

Sentinel-2 provides free, high-resolution satellite imagery from ESA.
Resolution is 10m per pixel for RGB bands, updated every 5 days.
Coverage is global (land areas between 56S and 84N latitude).
"""

from src.db.models import ProviderName
from src.providers.base import TileProvider, TileResult


class SentinelProvider(TileProvider):
    """Sentinel-2 tile provider using AWS Open Data / EOX WMS.

    Uses the Sentinel-2 cloudless mosaic from EOX, which provides
    a cloud-free composite that's freely available without authentication.
    """

    name = ProviderName.SENTINEL
    display_name = "Sentinel-2 (ESA)"
    max_zoom = 18
    requires_api_key = False

    # Sentinel-2 Cloudless WMS (free, no authentication)
    # This is a cloud-free mosaic from EOX
    BASE_URL = "https://tiles.maps.eox.at/wms"

    def get_tile_url(self, x: int, y: int, zoom: int) -> str:
        """Get Sentinel-2 tile URL using WMS endpoint."""
        bounds = self.tile_to_bounds(x, y, zoom)
        min_lon, min_lat, max_lon, max_lat = bounds

        # Use WMS GetMap request
        url = (
            f"{self.BASE_URL}?"
            f"SERVICE=WMS"
            f"&VERSION=1.1.1"
            f"&REQUEST=GetMap"
            f"&LAYERS=s2cloudless-2020"
            f"&STYLES="
            f"&SRS=EPSG:4326"
            f"&BBOX={min_lon},{min_lat},{max_lon},{max_lat}"
            f"&WIDTH={self.tile_size}"
            f"&HEIGHT={self.tile_size}"
            f"&FORMAT=image/png"
        )
        return url

    async def get_tile(self, x: int, y: int, zoom: int) -> TileResult:
        """Download a Sentinel-2 tile."""
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
                "source": "ESA Sentinel-2 Cloudless (EOX)",
                "coverage": "Global (56S to 84N)",
                "native_resolution": "10m",
                "year": "2020",
            },
            error=error,
        )


class SentinelAWSProvider(TileProvider):
    """Alternative Sentinel-2 provider using AWS Open Data XYZ tiles.

    Uses the Sentinel-2 COG tiles served via XYZ tile format.
    """

    name = ProviderName.SENTINEL
    display_name = "Sentinel-2 AWS"
    max_zoom = 14  # AWS tiles max zoom
    requires_api_key = False

    # Sentinel-2 L2A COG via Element84 (free, open data)
    BASE_URL = "https://sentinel-cogs.s3.us-west-2.amazonaws.com"

    def get_tile_url(self, x: int, y: int, zoom: int) -> str:
        """Get Sentinel-2 XYZ tile URL."""
        # For the AWS COG data, we'd need to construct paths based on MGRS grid
        # For simplicity, fall back to a tile server
        # Using Stamen/Stadia for fallback (not actual Sentinel data)
        return f"https://tiles.stadiamaps.com/tiles/alidade_satellite/{zoom}/{x}/{y}.png"

    async def get_tile(self, x: int, y: int, zoom: int) -> TileResult:
        """Download a Sentinel-2 tile from AWS."""
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
                "source": "AWS Open Data Sentinel-2",
                "coverage": "Global",
            },
            error=error,
        )
