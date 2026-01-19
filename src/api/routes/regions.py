"""Region management routes."""

import json
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.db import get_db
from src.db.models import ProviderName, Region, Tile, TileStatus
from src.providers import get_provider
from src.services.tile_manager import TileManager

router = APIRouter()


class RegionCreate(BaseModel):
    """Request to create a new region."""

    name: str
    description: Optional[str] = None
    min_lat: float = Field(..., ge=-90, le=90)
    max_lat: float = Field(..., ge=-90, le=90)
    min_lon: float = Field(..., ge=-180, le=180)
    max_lon: float = Field(..., ge=-180, le=180)
    geometry_geojson: Optional[str] = None
    target_gsd: float = Field(default=0.6, gt=0)
    target_zoom: Optional[int] = Field(default=None, ge=1, le=22)


class RegionResponse(BaseModel):
    """Region info response."""

    id: int
    name: str
    description: Optional[str]
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float
    target_gsd: float
    target_zoom: Optional[int]
    total_tiles: int
    downloaded_tiles: int
    is_complete: bool

    class Config:
        from_attributes = True


class RegionListResponse(BaseModel):
    """List of regions response."""

    regions: list[RegionResponse]
    total: int


class DownloadRequest(BaseModel):
    """Request to download tiles for a region."""

    providers: list[str] = Field(default=["naip"])
    zoom: Optional[int] = None


class DownloadStatus(BaseModel):
    """Download status response."""

    region_id: int
    total_tiles: int
    downloaded_tiles: int
    pending_tiles: int
    error_tiles: int
    is_complete: bool


@router.get("", response_model=RegionListResponse)
async def list_regions(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """List all regions."""
    regions = db.query(Region).offset(skip).limit(limit).all()
    total = db.query(Region).count()

    return RegionListResponse(
        regions=[RegionResponse.model_validate(r) for r in regions],
        total=total,
    )


@router.post("", response_model=RegionResponse)
async def create_region(
    region: RegionCreate,
    db: Session = Depends(get_db),
):
    """Create a new region of interest."""
    db_region = Region(
        name=region.name,
        description=region.description,
        min_lat=region.min_lat,
        max_lat=region.max_lat,
        min_lon=region.min_lon,
        max_lon=region.max_lon,
        geometry_geojson=region.geometry_geojson,
        target_gsd=region.target_gsd,
        target_zoom=region.target_zoom,
    )

    # Calculate number of tiles needed
    provider = get_provider(ProviderName.NAIP)
    zoom = region.target_zoom or 16  # Default zoom for ~0.6m GSD
    tiles = provider.bounds_to_tiles(
        region.min_lon, region.min_lat, region.max_lon, region.max_lat, zoom
    )
    db_region.total_tiles = len(tiles)

    db.add(db_region)
    db.commit()
    db.refresh(db_region)

    return RegionResponse.model_validate(db_region)


@router.get("/{region_id}", response_model=RegionResponse)
async def get_region(
    region_id: int,
    db: Session = Depends(get_db),
):
    """Get a specific region."""
    region = db.query(Region).filter(Region.id == region_id).first()
    if not region:
        raise HTTPException(status_code=404, detail="Region not found")

    return RegionResponse.model_validate(region)


@router.delete("/{region_id}")
async def delete_region(
    region_id: int,
    db: Session = Depends(get_db),
):
    """Delete a region and optionally its tiles."""
    region = db.query(Region).filter(Region.id == region_id).first()
    if not region:
        raise HTTPException(status_code=404, detail="Region not found")

    db.delete(region)
    db.commit()

    return {"message": "Region deleted", "id": region_id}


@router.post("/{region_id}/download", response_model=DownloadStatus)
async def start_download(
    region_id: int,
    request: DownloadRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Start downloading tiles for a region."""
    region = db.query(Region).filter(Region.id == region_id).first()
    if not region:
        raise HTTPException(status_code=404, detail="Region not found")

    # Validate providers
    for p in request.providers:
        try:
            ProviderName(p)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown provider: {p}")

    # Create tile manager and start download in background
    manager = TileManager(db)

    background_tasks.add_task(
        manager.download_region,
        region_id=region_id,
        provider_names=[ProviderName(p) for p in request.providers],
        zoom=request.zoom,
    )

    return DownloadStatus(
        region_id=region_id,
        total_tiles=region.total_tiles,
        downloaded_tiles=region.downloaded_tiles,
        pending_tiles=region.total_tiles - region.downloaded_tiles,
        error_tiles=0,
        is_complete=region.is_complete,
    )


@router.get("/{region_id}/status", response_model=DownloadStatus)
async def get_download_status(
    region_id: int,
    db: Session = Depends(get_db),
):
    """Get download status for a region."""
    region = db.query(Region).filter(Region.id == region_id).first()
    if not region:
        raise HTTPException(status_code=404, detail="Region not found")

    # Count tiles by status
    error_count = (
        db.query(Tile)
        .filter(Tile.region_id == region_id, Tile.status == TileStatus.ERROR)
        .count()
    )

    return DownloadStatus(
        region_id=region_id,
        total_tiles=region.total_tiles,
        downloaded_tiles=region.downloaded_tiles,
        pending_tiles=region.total_tiles - region.downloaded_tiles - error_count,
        error_tiles=error_count,
        is_complete=region.is_complete,
    )


@router.get("/{region_id}/tiles")
async def get_region_tiles(
    region_id: int,
    provider: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """Get tiles for a region with optional filtering."""
    region = db.query(Region).filter(Region.id == region_id).first()
    if not region:
        raise HTTPException(status_code=404, detail="Region not found")

    query = db.query(Tile).filter(Tile.region_id == region_id)

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
                "tile_x": t.tile_x,
                "tile_y": t.tile_y,
                "zoom": t.zoom,
                "status": t.status.value,
                "file_path": t.file_path,
                "gsd": t.gsd,
                "bounds": {
                    "min_lat": t.min_lat,
                    "max_lat": t.max_lat,
                    "min_lon": t.min_lon,
                    "max_lon": t.max_lon,
                },
            }
            for t in tiles
        ],
        "total": total,
        "skip": skip,
        "limit": limit,
    }
