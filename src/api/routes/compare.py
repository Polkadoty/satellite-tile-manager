"""Tile comparison routes."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.db import get_db
from src.db.models import Tile, TileComparison, TileStatus
from src.services.comparator import TileComparator

router = APIRouter()


class CompareRequest(BaseModel):
    """Request to compare two tiles."""

    tile_a_id: int
    tile_b_id: int


class ComparisonResponse(BaseModel):
    """Comparison result response."""

    id: int
    tile_a_id: int
    tile_b_id: int
    ssim_score: Optional[float]
    psnr_score: Optional[float]
    mse_score: Optional[float]
    histogram_correlation: Optional[float]
    feature_match_count: Optional[int]
    notes: Optional[str]

    class Config:
        from_attributes = True


class BulkCompareRequest(BaseModel):
    """Request to compare tiles at the same location across providers."""

    lat: float
    lon: float
    zoom: int = 16


@router.post("", response_model=ComparisonResponse)
async def compare_tiles(
    request: CompareRequest,
    db: Session = Depends(get_db),
):
    """Compare two tiles and store the results."""
    tile_a = db.query(Tile).filter(Tile.id == request.tile_a_id).first()
    tile_b = db.query(Tile).filter(Tile.id == request.tile_b_id).first()

    if not tile_a:
        raise HTTPException(status_code=404, detail=f"Tile A not found: {request.tile_a_id}")
    if not tile_b:
        raise HTTPException(status_code=404, detail=f"Tile B not found: {request.tile_b_id}")

    if tile_a.status != TileStatus.READY or tile_b.status != TileStatus.READY:
        raise HTTPException(status_code=400, detail="Both tiles must be downloaded")

    if not tile_a.file_path or not tile_b.file_path:
        raise HTTPException(status_code=400, detail="Both tiles must have files")

    # Check if comparison already exists
    existing = (
        db.query(TileComparison)
        .filter(
            ((TileComparison.tile_a_id == tile_a.id) & (TileComparison.tile_b_id == tile_b.id))
            | ((TileComparison.tile_a_id == tile_b.id) & (TileComparison.tile_b_id == tile_a.id))
        )
        .first()
    )

    if existing:
        return ComparisonResponse.model_validate(existing)

    # Perform comparison
    comparator = TileComparator()
    result = comparator.compare(tile_a.file_path, tile_b.file_path)

    # Calculate capture date difference
    capture_diff = None
    if tile_a.capture_date and tile_b.capture_date:
        capture_diff = abs((tile_a.capture_date - tile_b.capture_date).days)

    # Store comparison
    comparison = TileComparison(
        tile_a_id=tile_a.id,
        tile_b_id=tile_b.id,
        ssim_score=result.get("ssim"),
        psnr_score=result.get("psnr"),
        mse_score=result.get("mse"),
        histogram_correlation=result.get("histogram_correlation"),
        feature_match_count=result.get("feature_match_count"),
        capture_date_diff_days=capture_diff,
    )
    db.add(comparison)
    db.commit()
    db.refresh(comparison)

    return ComparisonResponse.model_validate(comparison)


@router.get("/{comparison_id}", response_model=ComparisonResponse)
async def get_comparison(
    comparison_id: int,
    db: Session = Depends(get_db),
):
    """Get a specific comparison."""
    comparison = db.query(TileComparison).filter(TileComparison.id == comparison_id).first()
    if not comparison:
        raise HTTPException(status_code=404, detail="Comparison not found")

    return ComparisonResponse.model_validate(comparison)


@router.get("/tile/{tile_id}")
async def get_tile_comparisons(
    tile_id: int,
    db: Session = Depends(get_db),
):
    """Get all comparisons involving a specific tile."""
    tile = db.query(Tile).filter(Tile.id == tile_id).first()
    if not tile:
        raise HTTPException(status_code=404, detail="Tile not found")

    comparisons = (
        db.query(TileComparison)
        .filter(
            (TileComparison.tile_a_id == tile_id) | (TileComparison.tile_b_id == tile_id)
        )
        .all()
    )

    return {
        "tile_id": tile_id,
        "comparisons": [
            ComparisonResponse.model_validate(c) for c in comparisons
        ],
    }


@router.post("/location")
async def compare_at_location(
    request: BulkCompareRequest,
    db: Session = Depends(get_db),
):
    """Find and compare all tiles at the same location across providers."""
    # Find all tiles that contain this coordinate
    tiles = (
        db.query(Tile)
        .filter(
            Tile.zoom == request.zoom,
            Tile.min_lat <= request.lat,
            Tile.max_lat >= request.lat,
            Tile.min_lon <= request.lon,
            Tile.max_lon >= request.lon,
            Tile.status == TileStatus.READY,
        )
        .all()
    )

    if len(tiles) < 2:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least 2 tiles at this location. Found {len(tiles)}",
        )

    # Compare all pairs
    comparisons = []
    comparator = TileComparator()

    for i, tile_a in enumerate(tiles):
        for tile_b in tiles[i + 1 :]:
            # Check if comparison exists
            existing = (
                db.query(TileComparison)
                .filter(
                    ((TileComparison.tile_a_id == tile_a.id) & (TileComparison.tile_b_id == tile_b.id))
                    | ((TileComparison.tile_a_id == tile_b.id) & (TileComparison.tile_b_id == tile_a.id))
                )
                .first()
            )

            if existing:
                comparisons.append(existing)
                continue

            # Perform comparison
            if tile_a.file_path and tile_b.file_path:
                result = comparator.compare(tile_a.file_path, tile_b.file_path)

                comparison = TileComparison(
                    tile_a_id=tile_a.id,
                    tile_b_id=tile_b.id,
                    ssim_score=result.get("ssim"),
                    psnr_score=result.get("psnr"),
                    mse_score=result.get("mse"),
                    histogram_correlation=result.get("histogram_correlation"),
                    feature_match_count=result.get("feature_match_count"),
                )
                db.add(comparison)
                comparisons.append(comparison)

    db.commit()

    return {
        "location": {"lat": request.lat, "lon": request.lon, "zoom": request.zoom},
        "tiles_found": len(tiles),
        "comparisons": [
            {
                "id": c.id,
                "tile_a_id": c.tile_a_id,
                "tile_b_id": c.tile_b_id,
                "ssim_score": c.ssim_score,
                "psnr_score": c.psnr_score,
            }
            for c in comparisons
        ],
    }
