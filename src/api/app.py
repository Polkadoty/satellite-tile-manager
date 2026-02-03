"""FastAPI application setup."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.config import settings
from src.db import init_db
from src.services import cleanup as cleanup_services, get_tile_cache


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    init_db()
    yield
    # Shutdown - cleanup HTTP clients and caches
    await cleanup_services()


app = FastAPI(
    title="Satellite Tile Manager",
    description="API for managing satellite map tiles for ML training and drone deployment",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for web interface
static_dir = Path(__file__).parent.parent / "web" / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Templates
templates_dir = Path(__file__).parent.parent / "web" / "templates"
templates_dir.mkdir(parents=True, exist_ok=True)
templates = Jinja2Templates(directory=str(templates_dir))

# Import and include routers
from src.api.routes import providers, regions, tiles, compare, export

app.include_router(providers.router, prefix="/api/v1/providers", tags=["providers"])
app.include_router(regions.router, prefix="/api/v1/regions", tags=["regions"])
app.include_router(tiles.router, prefix="/api/v1/tiles", tags=["tiles"])
app.include_router(compare.router, prefix="/api/v1/compare", tags=["compare"])
app.include_router(export.router, prefix="/api/v1/export", tags=["export"])


@app.get("/")
async def root():
    """Root endpoint redirects to web interface."""
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url="/web")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "0.1.0"}


@app.get("/stats")
async def get_stats():
    """Get application statistics including cache metrics."""
    cache = get_tile_cache()
    return {
        "status": "healthy",
        "version": "0.1.0",
        "cache": cache.stats(),
    }


# Web interface routes
from src.api.routes import web

app.include_router(web.router, prefix="/web", tags=["web"])
