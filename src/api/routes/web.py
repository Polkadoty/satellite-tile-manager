"""Web interface routes."""

import os
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from src.config import settings
from src.db import get_db
from src.db.models import Region, Tile, TileStatus

router = APIRouter()

# Find templates directory - handle both local and serverless paths
templates_dir = Path(__file__).parent.parent.parent / "web" / "templates"
if not templates_dir.exists():
    # Try alternative paths for serverless
    alt_paths = [
        Path("/var/task/src/web/templates"),
        Path(os.getcwd()) / "src" / "web" / "templates",
    ]
    for alt_path in alt_paths:
        if alt_path.exists():
            templates_dir = alt_path
            break

templates = Jinja2Templates(directory=str(templates_dir))


def _init_db_if_needed():
    """Initialize database in serverless mode if not already done."""
    if settings.is_serverless:
        from src.db import init_db
        try:
            init_db()
        except Exception:
            pass  # Already initialized or will fail gracefully


@router.get("", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)):
    """Main web interface."""
    _init_db_if_needed()

    try:
        regions = db.query(Region).order_by(Region.created_at.desc()).limit(10).all()
        total_tiles = db.query(Tile).filter(Tile.status == TileStatus.READY).count()
    except Exception:
        regions = []
        total_tiles = 0

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
    _init_db_if_needed()

    try:
        regions = db.query(Region).order_by(Region.created_at.desc()).all()
    except Exception:
        regions = []

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
    _init_db_if_needed()

    try:
        region = db.query(Region).filter(Region.id == region_id).first()
    except Exception:
        region = None

    if not region:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": "Region not found"},
            status_code=404,
        )

    try:
        tiles = (
            db.query(Tile)
            .filter(Tile.region_id == region_id)
            .order_by(Tile.tile_x, Tile.tile_y)
            .all()
        )
    except Exception:
        tiles = []

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
    _init_db_if_needed()

    try:
        regions = db.query(Region).filter(Region.is_complete == True).all()
    except Exception:
        regions = []

    return templates.TemplateResponse(
        "export.html",
        {
            "request": request,
            "regions": regions,
        },
    )
