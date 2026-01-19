"""Web interface routes."""

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from src.db import get_db
from src.db.models import Region, Tile, TileStatus

router = APIRouter()

templates_dir = Path(__file__).parent.parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


@router.get("", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)):
    """Main web interface."""
    regions = db.query(Region).order_by(Region.created_at.desc()).limit(10).all()
    total_tiles = db.query(Tile).filter(Tile.status == TileStatus.READY).count()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "regions": regions,
            "total_tiles": total_tiles,
        },
    )


@router.get("/map", response_class=HTMLResponse)
async def map_view(request: Request):
    """Interactive map for selecting areas."""
    return templates.TemplateResponse(
        "map.html",
        {"request": request},
    )


@router.get("/regions", response_class=HTMLResponse)
async def regions_view(request: Request, db: Session = Depends(get_db)):
    """Region management page."""
    regions = db.query(Region).order_by(Region.created_at.desc()).all()

    return templates.TemplateResponse(
        "regions.html",
        {
            "request": request,
            "regions": regions,
        },
    )


@router.get("/regions/{region_id}", response_class=HTMLResponse)
async def region_detail(request: Request, region_id: int, db: Session = Depends(get_db)):
    """Region detail page."""
    region = db.query(Region).filter(Region.id == region_id).first()
    if not region:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": "Region not found"},
            status_code=404,
        )

    tiles = (
        db.query(Tile)
        .filter(Tile.region_id == region_id)
        .order_by(Tile.tile_x, Tile.tile_y)
        .all()
    )

    return templates.TemplateResponse(
        "region_detail.html",
        {
            "request": request,
            "region": region,
            "tiles": tiles,
        },
    )


@router.get("/compare", response_class=HTMLResponse)
async def compare_view(request: Request, db: Session = Depends(get_db)):
    """Tile comparison page."""
    return templates.TemplateResponse(
        "compare.html",
        {"request": request},
    )


@router.get("/export", response_class=HTMLResponse)
async def export_view(request: Request, db: Session = Depends(get_db)):
    """Export management page."""
    regions = db.query(Region).filter(Region.is_complete == True).all()

    return templates.TemplateResponse(
        "export.html",
        {
            "request": request,
            "regions": regions,
        },
    )
