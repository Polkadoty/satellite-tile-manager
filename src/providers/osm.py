"""OpenStreetMap tile provider.

OpenStreetMap provides free, community-created map tiles.
Note: OSM tiles are vector/rendered map tiles, not satellite imagery,
but they're useful for reference and context.
"""

from src.db.models import ProviderName
from src.providers.base import TileProvider, TileResult


class OSMProvider(TileProvider):
    """OpenStreetMap tile provider using standard tile servers."""

    name = ProviderName.OSM
    display_name = "OpenStreetMap"
    max_zoom = 19
    requires_api_key = False

    # OSM tile servers (use round-robin for load balancing)
    TILE_SERVERS = [
        "https://a.tile.openstreetmap.org",
        "https://b.tile.openstreetmap.org",
        "https://c.tile.openstreetmap.org",
    ]

    def __init__(self):
        super().__init__()
        self._server_index = 0

    def _get_server(self) -> str:
        """Get next tile server (round-robin)."""
        server = self.TILE_SERVERS[self._server_index]
        self._server_index = (self._server_index + 1) % len(self.TILE_SERVERS)
        return server

    def get_tile_url(self, x: int, y: int, zoom: int) -> str:
        """Get OSM tile URL using XYZ scheme."""
        server = self._get_server()
        return f"{server}/{zoom}/{x}/{y}.png"

    async def get_tile(self, x: int, y: int, zoom: int) -> TileResult:
        """Download an OSM tile."""
        bounds = self.tile_to_bounds(x, y, zoom)
        min_lon, min_lat, max_lon, max_lat = bounds
        center_lat = (min_lat + max_lat) / 2

        gsd = self.calculate_gsd(center_lat, zoom)
        save_path = self.get_storage_path(x, y, zoom, "png")

        url = self.get_tile_url(x, y, zoom)

        # OSM requires a proper User-Agent
        try:
            response = await self.client.get(
                url,
                headers={"User-Agent": "SatelliteTileManager/1.0 (https://github.com/satellite-tile-manager)"}
            )
            response.raise_for_status()
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(response.content)
            success, error = True, None
        except Exception as e:
            success, error = False, str(e)

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
                "source": "OpenStreetMap",
                "type": "rendered_map",
                "license": "ODbL",
            },
            error=error,
        )


class OSMSatelliteProvider(TileProvider):
    """OSM-compatible satellite imagery from various open sources.

    Uses imagery from providers that offer OSM-compatible tile services.
    """

    name = ProviderName.OSM
    display_name = "OSM Satellite"
    max_zoom = 19
    requires_api_key = False

    # CARTO satellite basemap (free tier)
    BASE_URL = "https://basemaps.cartocdn.com/rastertiles/voyager"

    def get_tile_url(self, x: int, y: int, zoom: int) -> str:
        """Get satellite tile URL."""
        return f"{self.BASE_URL}/{zoom}/{x}/{y}.png"

    async def get_tile(self, x: int, y: int, zoom: int) -> TileResult:
        """Download a satellite tile."""
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
                "source": "CARTO Basemaps",
                "type": "satellite_hybrid",
            },
            error=error,
        )
