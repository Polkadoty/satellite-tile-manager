"""Export routes for ML training and drone deployment."""

import json
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.db import get_db
from src.db.models import ProviderName, Region, Tile, TileStatus

router = APIRouter()


class ExportRequest(BaseModel):
    """Export request parameters."""

    region_id: Optional[int] = None
    min_lat: Optional[float] = None
    max_lat: Optional[float] = None
    min_lon: Optional[float] = None
    max_lon: Optional[float] = None
    zoom: Optional[int] = None
    provider: Optional[str] = None
    format: str = "zip"  # zip, geojson, manifest


class ManifestEntry(BaseModel):
    """Entry in the export manifest."""

    tile_id: int
    file_path: str
    provider: str
    tile_x: int
    tile_y: int
    zoom: int
    gsd: float
    bounds: dict
    center: dict


@router.post("/manifest")
async def generate_manifest(
    request: ExportRequest,
    db: Session = Depends(get_db),
):
    """Generate a manifest of tiles for export.

    Returns a JSON manifest that can be used by training pipelines
    or drone deployment tools to access tiles.
    """
    query = db.query(Tile).filter(Tile.status == TileStatus.READY)

    if request.region_id:
        region = db.query(Region).filter(Region.id == request.region_id).first()
        if not region:
            raise HTTPException(status_code=404, detail="Region not found")
        query = query.filter(Tile.region_id == request.region_id)

    if request.min_lat and request.max_lat and request.min_lon and request.max_lon:
        query = query.filter(
            Tile.min_lat <= request.max_lat,
            Tile.max_lat >= request.min_lat,
            Tile.min_lon <= request.max_lon,
            Tile.max_lon >= request.min_lon,
        )

    if request.zoom:
        query = query.filter(Tile.zoom == request.zoom)

    if request.provider:
        try:
            provider_name = ProviderName(request.provider)
            query = query.join(Tile.provider).filter(
                Tile.provider.has(name=provider_name)
            )
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown provider: {request.provider}")

    tiles = query.all()

    manifest = {
        "version": "1.0",
        "tile_count": len(tiles),
        "bounds": None,
        "tiles": [],
    }

    if tiles:
        min_lat = min(t.min_lat for t in tiles)
        max_lat = max(t.max_lat for t in tiles)
        min_lon = min(t.min_lon for t in tiles)
        max_lon = max(t.max_lon for t in tiles)
        manifest["bounds"] = {
            "min_lat": min_lat,
            "max_lat": max_lat,
            "min_lon": min_lon,
            "max_lon": max_lon,
        }

    for tile in tiles:
        manifest["tiles"].append(
            {
                "tile_id": tile.id,
                "file_path": tile.file_path,
                "provider": tile.provider.name.value if tile.provider else None,
                "tile_x": tile.tile_x,
                "tile_y": tile.tile_y,
                "zoom": tile.zoom,
                "gsd": tile.gsd,
                "bounds": {
                    "min_lat": tile.min_lat,
                    "max_lat": tile.max_lat,
                    "min_lon": tile.min_lon,
                    "max_lon": tile.max_lon,
                },
                "center": {"lat": tile.center_lat, "lon": tile.center_lon},
            }
        )

    return manifest


@router.post("/zip")
async def export_zip(
    request: ExportRequest,
    db: Session = Depends(get_db),
):
    """Export tiles as a ZIP archive.

    Creates a ZIP file containing:
    - All tile images
    - A manifest.json with tile metadata
    - A geojson file with tile boundaries (optional)
    """
    query = db.query(Tile).filter(Tile.status == TileStatus.READY)

    if request.region_id:
        region = db.query(Region).filter(Region.id == request.region_id).first()
        if not region:
            raise HTTPException(status_code=404, detail="Region not found")
        query = query.filter(Tile.region_id == request.region_id)

    if request.min_lat and request.max_lat and request.min_lon and request.max_lon:
        query = query.filter(
            Tile.min_lat <= request.max_lat,
            Tile.max_lat >= request.min_lat,
            Tile.min_lon <= request.max_lon,
            Tile.max_lon >= request.min_lon,
        )

    if request.zoom:
        query = query.filter(Tile.zoom == request.zoom)

    if request.provider:
        try:
            provider_name = ProviderName(request.provider)
            query = query.join(Tile.provider).filter(
                Tile.provider.has(name=provider_name)
            )
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown provider: {request.provider}")

    tiles = query.all()

    if not tiles:
        raise HTTPException(status_code=404, detail="No tiles found matching criteria")

    # Create temporary ZIP file
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")

    with zipfile.ZipFile(temp_file.name, "w", zipfile.ZIP_DEFLATED) as zf:
        manifest = {"version": "1.0", "tile_count": len(tiles), "tiles": []}

        for tile in tiles:
            if tile.file_path and Path(tile.file_path).exists():
                # Add tile to zip with structured path
                provider_name = tile.provider.name.value if tile.provider else "unknown"
                archive_path = f"{provider_name}/{tile.zoom}/{tile.tile_x}/{tile.tile_y}.{tile.file_format}"
                zf.write(tile.file_path, archive_path)

                manifest["tiles"].append(
                    {
                        "file": archive_path,
                        "tile_id": tile.id,
                        "provider": provider_name,
                        "tile_x": tile.tile_x,
                        "tile_y": tile.tile_y,
                        "zoom": tile.zoom,
                        "gsd": tile.gsd,
                        "bounds": {
                            "min_lat": tile.min_lat,
                            "max_lat": tile.max_lat,
                            "min_lon": tile.min_lon,
                            "max_lon": tile.max_lon,
                        },
                        "center": {"lat": tile.center_lat, "lon": tile.center_lon},
                    }
                )

        # Add manifest
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

        # Add GeoJSON
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "tile_id": t["tile_id"],
                        "provider": t["provider"],
                        "zoom": t["zoom"],
                        "gsd": t["gsd"],
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [t["bounds"]["min_lon"], t["bounds"]["min_lat"]],
                                [t["bounds"]["max_lon"], t["bounds"]["min_lat"]],
                                [t["bounds"]["max_lon"], t["bounds"]["max_lat"]],
                                [t["bounds"]["min_lon"], t["bounds"]["max_lat"]],
                                [t["bounds"]["min_lon"], t["bounds"]["min_lat"]],
                            ]
                        ],
                    },
                }
                for t in manifest["tiles"]
            ],
        }
        zf.writestr("tiles.geojson", json.dumps(geojson, indent=2))

    return FileResponse(
        path=temp_file.name,
        media_type="application/zip",
        filename="tiles_export.zip",
    )


@router.get("/drone-package")
async def export_drone_package(
    region_id: int,
    target_gsd: float = Query(1.0, description="Target GSD in meters"),
    db: Session = Depends(get_db),
):
    """Export a drone-optimized tile package.

    Creates a package optimized for loading onto drone edge devices:
    - Tiles organized by geographic grid
    - Metadata for quick spatial lookup
    - Optimized file format for memory-mapped access
    """
    region = db.query(Region).filter(Region.id == region_id).first()
    if not region:
        raise HTTPException(status_code=404, detail="Region not found")

    tiles = (
        db.query(Tile)
        .filter(Tile.region_id == region_id, Tile.status == TileStatus.READY)
        .all()
    )

    if not tiles:
        raise HTTPException(status_code=404, detail="No tiles found for region")

    # Create drone package manifest
    package = {
        "version": "1.0",
        "region": {
            "id": region.id,
            "name": region.name,
            "bounds": {
                "min_lat": region.min_lat,
                "max_lat": region.max_lat,
                "min_lon": region.min_lon,
                "max_lon": region.max_lon,
            },
        },
        "target_gsd": target_gsd,
        "tile_count": len(tiles),
        "tiles": [],
        "spatial_index": [],
    }

    # Build spatial index for quick lookup
    # Divide region into grid cells for fast tile lookup
    grid_size = 0.01  # ~1km grid cells
    lat_range = region.max_lat - region.min_lat
    lon_range = region.max_lon - region.min_lon
    n_lat = max(1, int(lat_range / grid_size))
    n_lon = max(1, int(lon_range / grid_size))

    grid = [[[] for _ in range(n_lon)] for _ in range(n_lat)]

    for tile in tiles:
        center_lat = tile.center_lat
        center_lon = tile.center_lon

        # Find grid cell
        lat_idx = min(n_lat - 1, int((center_lat - region.min_lat) / grid_size))
        lon_idx = min(n_lon - 1, int((center_lon - region.min_lon) / grid_size))

        grid[lat_idx][lon_idx].append(tile.id)

        package["tiles"].append(
            {
                "id": tile.id,
                "file": tile.file_path,
                "x": tile.tile_x,
                "y": tile.tile_y,
                "z": tile.zoom,
                "gsd": tile.gsd,
                "lat": tile.center_lat,
                "lon": tile.center_lon,
            }
        )

    package["spatial_index"] = {
        "grid_size": grid_size,
        "n_lat": n_lat,
        "n_lon": n_lon,
        "origin": {"lat": region.min_lat, "lon": region.min_lon},
        "cells": grid,
    }

    return package
