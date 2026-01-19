"""Tile management service."""

import asyncio
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from src.config import settings
from src.db.models import Provider, ProviderName, Region, Tile, TileStatus
from src.providers import get_provider


class TileManager:
    """Manages tile downloads, storage, and cleanup."""

    def __init__(self, db: Session):
        self.db = db

    def ensure_provider(self, name: ProviderName) -> Provider:
        """Ensure provider exists in database."""
        provider = self.db.query(Provider).filter(Provider.name == name).first()
        if not provider:
            tile_provider = get_provider(name)
            provider = Provider(
                name=name,
                display_name=tile_provider.display_name,
                max_zoom=tile_provider.max_zoom,
                api_key_required=tile_provider.requires_api_key,
            )
            self.db.add(provider)
            self.db.commit()
            self.db.refresh(provider)
        return provider

    async def download_region(
        self,
        region_id: int,
        provider_names: list[ProviderName],
        zoom: Optional[int] = None,
    ):
        """Download all tiles for a region from specified providers."""
        region = self.db.query(Region).filter(Region.id == region_id).first()
        if not region:
            raise ValueError(f"Region not found: {region_id}")

        # Use specified zoom or calculate from target GSD
        if zoom is None:
            zoom = region.target_zoom or 16

        for provider_name in provider_names:
            await self._download_region_from_provider(region, provider_name, zoom)

        # Update region status
        region.is_complete = True
        self.db.commit()

    async def _download_region_from_provider(
        self,
        region: Region,
        provider_name: ProviderName,
        zoom: int,
    ):
        """Download tiles for a region from a single provider."""
        provider = get_provider(provider_name)
        db_provider = self.ensure_provider(provider_name)

        # Get list of tiles needed
        tiles = provider.bounds_to_tiles(
            region.min_lon, region.min_lat, region.max_lon, region.max_lat, zoom
        )

        # Update region total
        region.total_tiles = len(tiles) * len([provider_name])

        # Download tiles with concurrency limit
        semaphore = asyncio.Semaphore(settings.max_concurrent_downloads)

        async def download_with_limit(x: int, y: int):
            async with semaphore:
                return await self._download_tile(
                    provider, db_provider, region, x, y, zoom
                )

        tasks = [download_with_limit(x, y) for x, y in tiles]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Count successful downloads
        success_count = sum(1 for r in results if r is True)
        region.downloaded_tiles = success_count
        self.db.commit()

    async def _download_tile(
        self,
        provider,
        db_provider: Provider,
        region: Region,
        x: int,
        y: int,
        zoom: int,
    ) -> bool:
        """Download a single tile."""
        # Check if tile already exists
        existing = (
            self.db.query(Tile)
            .filter(
                Tile.provider_id == db_provider.id,
                Tile.tile_x == x,
                Tile.tile_y == y,
                Tile.zoom == zoom,
            )
            .first()
        )

        if existing and existing.status == TileStatus.READY:
            return True

        # Create or update tile record
        if existing:
            tile = existing
            tile.status = TileStatus.DOWNLOADING
        else:
            bounds = provider.tile_to_bounds(x, y, zoom)
            center_lat = (bounds[1] + bounds[3]) / 2
            center_lon = (bounds[0] + bounds[2]) / 2

            tile = Tile(
                provider_id=db_provider.id,
                region_id=region.id,
                tile_x=x,
                tile_y=y,
                zoom=zoom,
                min_lon=bounds[0],
                min_lat=bounds[1],
                max_lon=bounds[2],
                max_lat=bounds[3],
                center_lat=center_lat,
                center_lon=center_lon,
                gsd=provider.calculate_gsd(center_lat, zoom),
                status=TileStatus.DOWNLOADING,
            )
            self.db.add(tile)

        self.db.commit()

        try:
            result = await provider.get_tile(x, y, zoom)

            if result.success:
                tile.status = TileStatus.READY
                tile.file_path = str(result.file_path)
                tile.file_size_bytes = result.file_size
                tile.file_format = result.file_format
                tile.download_date = datetime.utcnow()
                tile.metadata = result.metadata

                # Calculate checksum
                if result.file_path and result.file_path.exists():
                    tile.checksum_sha256 = self._calculate_checksum(result.file_path)

                self.db.commit()
                return True
            else:
                tile.status = TileStatus.ERROR
                tile.error_message = result.error
                self.db.commit()
                return False

        except Exception as e:
            tile.status = TileStatus.ERROR
            tile.error_message = str(e)
            self.db.commit()
            return False

    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def cleanup_duplicates(self, region_id: Optional[int] = None):
        """Remove duplicate tiles (same coordinates, different providers kept)."""
        query = self.db.query(Tile)
        if region_id:
            query = query.filter(Tile.region_id == region_id)

        tiles = query.all()

        # Group by coordinates
        coord_map: dict[tuple, list[Tile]] = {}
        for tile in tiles:
            key = (tile.zoom, tile.tile_x, tile.tile_y, tile.provider_id)
            if key not in coord_map:
                coord_map[key] = []
            coord_map[key].append(tile)

        # Remove duplicates (keep the newest)
        removed = 0
        for key, tile_list in coord_map.items():
            if len(tile_list) > 1:
                # Sort by download date, keep newest
                tile_list.sort(key=lambda t: t.download_date or datetime.min, reverse=True)
                for tile in tile_list[1:]:
                    if tile.file_path:
                        path = Path(tile.file_path)
                        if path.exists():
                            path.unlink()
                    self.db.delete(tile)
                    removed += 1

        self.db.commit()
        return removed

    def cleanup_missing_files(self, region_id: Optional[int] = None):
        """Mark tiles with missing files as errors."""
        query = self.db.query(Tile).filter(Tile.status == TileStatus.READY)
        if region_id:
            query = query.filter(Tile.region_id == region_id)

        tiles = query.all()
        updated = 0

        for tile in tiles:
            if tile.file_path:
                path = Path(tile.file_path)
                if not path.exists():
                    tile.status = TileStatus.ERROR
                    tile.error_message = "File not found"
                    updated += 1

        self.db.commit()
        return updated

    def verify_coverage(self, region_id: int) -> dict:
        """Verify tile coverage for a region.

        Returns statistics about coverage completeness.
        """
        region = self.db.query(Region).filter(Region.id == region_id).first()
        if not region:
            raise ValueError(f"Region not found: {region_id}")

        tiles = (
            self.db.query(Tile)
            .filter(Tile.region_id == region_id, Tile.status == TileStatus.READY)
            .all()
        )

        # Check for gaps
        zoom = region.target_zoom or 16
        provider = get_provider(ProviderName.NAIP)
        expected_tiles = set(
            provider.bounds_to_tiles(
                region.min_lon, region.min_lat, region.max_lon, region.max_lat, zoom
            )
        )

        actual_tiles = set((t.tile_x, t.tile_y) for t in tiles)
        missing = expected_tiles - actual_tiles
        extra = actual_tiles - expected_tiles

        return {
            "region_id": region_id,
            "expected_tiles": len(expected_tiles),
            "actual_tiles": len(actual_tiles),
            "missing_count": len(missing),
            "extra_count": len(extra),
            "coverage_pct": len(actual_tiles) / len(expected_tiles) * 100 if expected_tiles else 0,
            "missing_coords": list(missing)[:20],  # Limit for response size
        }
