"""Tile management routes."""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.db import get_db
from src.db.models import ProviderName, Tile, TileStatus
from src.providers import get_provider

router = APIRouter()


class TileQuery(BaseModel):
    """Tile query parameters."""

    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float
    zoom: Optional[int] = None
    provider: Optional[str] = None


class TileResponse(BaseModel):
    """Tile info response."""

    id: int
    provider: str
    tile_x: int
    tile_y: int
    zoom: int
    gsd: float
    status: str
    file_path: Optional[str]
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float
    center_lat: float
    center_lon: float

    class Config:
        from_attributes = True


@router.get("/query")
async def query_tiles(
    min_lat: float = Query(..., ge=-90, le=90),
    max_lat: float = Query(..., ge=-90, le=90),
    min_lon: float = Query(..., ge=-180, le=180),
    max_lon: float = Query(..., ge=-180, le=180),
    zoom: Optional[int] = Query(None, ge=1, le=22),
    provider: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """Query tiles within a bounding box."""
    query = db.query(Tile).filter(
        Tile.min_lat <= max_lat,
        Tile.max_lat >= min_lat,
        Tile.min_lon <= max_lon,
        Tile.max_lon >= min_lon,
    )

    if zoom:
        query = query.filter(Tile.zoom == zoom)

    if provider:
        try:
            provider_name = ProviderName(provider)
            query = query.join(Tile.provider).filter(
                Tile.provider.has(name=provider_name)
            )
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    if status:
        try:
            tile_status = TileStatus(status)
            query = query.filter(Tile.status == tile_status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown status: {status}")

    total = query.count()
    tiles = query.offset(skip).limit(limit).all()

    return {
        "tiles": [
            {
                "id": t.id,
                "provider": t.provider.name.value if t.provider else None,
                "tile_x": t.tile_x,
                "tile_y": t.tile_y,
                "zoom": t.zoom,
                "status": t.status.value,
                "gsd": t.gsd,
                "file_path": t.file_path,
                "bounds": {
                    "min_lat": t.min_lat,
                    "max_lat": t.max_lat,
                    "min_lon": t.min_lon,
                    "max_lon": t.max_lon,
                },
                "center": {"lat": t.center_lat, "lon": t.center_lon},
            }
            for t in tiles
        ],
        "total": total,
        "bounds": {
            "min_lat": min_lat,
            "max_lat": max_lat,
            "min_lon": min_lon,
            "max_lon": max_lon,
        },
    }


@router.get("/{tile_id}")
async def get_tile(
    tile_id: int,
    db: Session = Depends(get_db),
):
    """Get tile metadata by ID."""
    tile = db.query(Tile).filter(Tile.id == tile_id).first()
    if not tile:
        raise HTTPException(status_code=404, detail="Tile not found")

    return {
        "id": tile.id,
        "provider": tile.provider.name.value if tile.provider else None,
        "tile_x": tile.tile_x,
        "tile_y": tile.tile_y,
        "zoom": tile.zoom,
        "status": tile.status.value,
        "gsd": tile.gsd,
        "file_path": tile.file_path,
        "file_size": tile.file_size_bytes,
        "checksum": tile.checksum_sha256,
        "bounds": {
            "min_lat": tile.min_lat,
            "max_lat": tile.max_lat,
            "min_lon": tile.min_lon,
            "max_lon": tile.max_lon,
        },
        "center": {"lat": tile.center_lat, "lon": tile.center_lon},
        "quality": {
            "has_data": tile.has_data,
            "cloud_cover_pct": tile.cloud_cover_pct,
            "quality_score": tile.quality_score,
        },
        "extra_data": tile.extra_data,
        "capture_date": tile.capture_date.isoformat() if tile.capture_date else None,
        "download_date": tile.download_date.isoformat() if tile.download_date else None,
    }


@router.get("/{tile_id}/image")
async def get_tile_image(
    tile_id: int,
    db: Session = Depends(get_db),
):
    """Get tile image file."""
    tile = db.query(Tile).filter(Tile.id == tile_id).first()
    if not tile:
        raise HTTPException(status_code=404, detail="Tile not found")

    if not tile.file_path:
        raise HTTPException(status_code=404, detail="Tile image not available")

    file_path = Path(tile.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Tile image file not found")

    media_type = "image/tiff" if tile.file_format == "tif" else f"image/{tile.file_format}"

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=file_path.name,
    )


@router.delete("/{tile_id}")
async def delete_tile(
    tile_id: int,
    delete_file: bool = True,
    db: Session = Depends(get_db),
):
    """Delete a tile record and optionally its file."""
    tile = db.query(Tile).filter(Tile.id == tile_id).first()
    if not tile:
        raise HTTPException(status_code=404, detail="Tile not found")

    if delete_file and tile.file_path:
        file_path = Path(tile.file_path)
        if file_path.exists():
            file_path.unlink()

    db.delete(tile)
    db.commit()

    return {"message": "Tile deleted", "id": tile_id}


@router.post("/download")
async def download_single_tile(
    provider: str,
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    zoom: int = Query(16, ge=1, le=22),
    db: Session = Depends(get_db),
):
    """Download a single tile at the given coordinates."""
    try:
        provider_name = ProviderName(provider)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    tile_provider = get_provider(provider_name)
    x, y = tile_provider.coords_to_tile(lon, lat, zoom)

    # Check if tile already exists
    existing = (
        db.query(Tile)
        .filter(
            Tile.tile_x == x,
            Tile.tile_y == y,
            Tile.zoom == zoom,
        )
        .join(Tile.provider)
        .filter(Tile.provider.has(name=provider_name))
        .first()
    )

    if existing and existing.status == TileStatus.READY:
        return {
            "message": "Tile already exists",
            "tile_id": existing.id,
            "file_path": existing.file_path,
        }

    # Download the tile
    import asyncio

    result = asyncio.get_event_loop().run_until_complete(
        tile_provider.get_tile(x, y, zoom)
    )

    if not result.success:
        raise HTTPException(status_code=500, detail=f"Download failed: {result.error}")

    # Get or create provider record
    from src.db.models import Provider

    db_provider = db.query(Provider).filter(Provider.name == provider_name).first()
    if not db_provider:
        db_provider = Provider(
            name=provider_name,
            display_name=tile_provider.display_name,
            max_zoom=tile_provider.max_zoom,
            api_key_required=tile_provider.requires_api_key,
        )
        db.add(db_provider)
        db.commit()
        db.refresh(db_provider)

    # Create tile record
    tile = Tile(
        provider_id=db_provider.id,
        tile_x=x,
        tile_y=y,
        zoom=zoom,
        min_lat=result.min_lat,
        max_lat=result.max_lat,
        min_lon=result.min_lon,
        max_lon=result.max_lon,
        center_lat=(result.min_lat + result.max_lat) / 2,
        center_lon=(result.min_lon + result.max_lon) / 2,
        gsd=result.gsd,
        file_path=str(result.file_path) if result.file_path else None,
        file_size_bytes=result.file_size,
        file_format=result.file_format,
        status=TileStatus.READY,
        extra_data=result.metadata,
    )
    db.add(tile)
    db.commit()
    db.refresh(tile)

    return {
        "message": "Tile downloaded",
        "tile_id": tile.id,
        "file_path": tile.file_path,
        "gsd": tile.gsd,
        "bounds": {
            "min_lat": tile.min_lat,
            "max_lat": tile.max_lat,
            "min_lon": tile.min_lon,
            "max_lon": tile.max_lon,
        },
    }
