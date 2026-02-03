"""Database models for satellite tile management."""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


class ProviderName(str, enum.Enum):
    """Supported tile providers."""

    NAIP = "naip"
    GOOGLE = "google"
    BING = "bing"
    MAPBOX = "mapbox"
    OSM = "osm"
    SENTINEL = "sentinel"
    ESRI = "esri"
    CUSTOM = "custom"


class TileStatus(str, enum.Enum):
    """Tile processing status."""

    PENDING = "pending"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"


class Provider(Base):
    """Tile provider configuration."""

    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[ProviderName] = mapped_column(Enum(ProviderName), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    base_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    api_key_required: Mapped[bool] = mapped_column(Boolean, default=False)
    max_zoom: Mapped[int] = mapped_column(Integer, default=20)
    default_gsd: Mapped[float] = mapped_column(Float, default=0.6)  # meters per pixel
    attribution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships
    tiles: Mapped[list["Tile"]] = relationship("Tile", back_populates="provider")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Region(Base):
    """User-defined region of interest."""

    __tablename__ = "regions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Bounding box (WGS84)
    min_lat: Mapped[float] = mapped_column(Float)
    max_lat: Mapped[float] = mapped_column(Float)
    min_lon: Mapped[float] = mapped_column(Float)
    max_lon: Mapped[float] = mapped_column(Float)

    # Optional polygon geometry stored as GeoJSON
    geometry_geojson: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Target parameters
    target_gsd: Mapped[float] = mapped_column(Float, default=0.6)  # meters per pixel
    target_zoom: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Status
    total_tiles: Mapped[int] = mapped_column(Integer, default=0)
    downloaded_tiles: Mapped[int] = mapped_column(Integer, default=0)
    is_complete: Mapped[bool] = mapped_column(Boolean, default=False)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    tiles: Mapped[list["Tile"]] = relationship("Tile", back_populates="region")

    __table_args__ = (Index("idx_region_bounds", "min_lat", "max_lat", "min_lon", "max_lon"),)


class Tile(Base):
    """Individual satellite map tile."""

    __tablename__ = "tiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Provider relationship
    provider_id: Mapped[int] = mapped_column(Integer, ForeignKey("providers.id"))
    provider: Mapped["Provider"] = relationship("Provider", back_populates="tiles")

    # Region relationship (optional)
    region_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("regions.id"), nullable=True
    )
    region: Mapped[Optional["Region"]] = relationship("Region", back_populates="tiles")

    # Tile coordinates (standard web mercator tile scheme)
    zoom: Mapped[int] = mapped_column(Integer)
    tile_x: Mapped[int] = mapped_column(Integer)
    tile_y: Mapped[int] = mapped_column(Integer)

    # Geographic bounds (WGS84)
    min_lat: Mapped[float] = mapped_column(Float)
    max_lat: Mapped[float] = mapped_column(Float)
    min_lon: Mapped[float] = mapped_column(Float)
    max_lon: Mapped[float] = mapped_column(Float)

    # Center point for quick queries
    center_lat: Mapped[float] = mapped_column(Float)
    center_lon: Mapped[float] = mapped_column(Float)

    # Resolution
    gsd: Mapped[float] = mapped_column(Float)  # Ground sampling distance (meters/pixel)
    width_pixels: Mapped[int] = mapped_column(Integer, default=256)
    height_pixels: Mapped[int] = mapped_column(Integer, default=256)

    # File info
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    file_format: Mapped[str] = mapped_column(String(20), default="tif")
    checksum_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Status
    status: Mapped[TileStatus] = mapped_column(Enum(TileStatus), default=TileStatus.PENDING)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Quality metrics
    has_data: Mapped[bool] = mapped_column(Boolean, default=True)  # False if blank/missing
    cloud_cover_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0-1

    # Temporal info
    capture_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    download_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Metadata from provider
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint("provider_id", "zoom", "tile_x", "tile_y", name="uq_tile_coords"),
        Index("idx_tile_bounds", "min_lat", "max_lat", "min_lon", "max_lon"),
        Index("idx_tile_center", "center_lat", "center_lon"),
        Index("idx_tile_status", "status"),
        Index("idx_tile_provider_zoom", "provider_id", "zoom"),
    )


class TileComparison(Base):
    """Comparison metrics between tiles from different providers."""

    __tablename__ = "tile_comparisons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # The two tiles being compared
    tile_a_id: Mapped[int] = mapped_column(Integer, ForeignKey("tiles.id"))
    tile_b_id: Mapped[int] = mapped_column(Integer, ForeignKey("tiles.id"))

    # Comparison metrics
    ssim_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Structural similarity
    psnr_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Peak SNR
    mse_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Mean squared error
    histogram_correlation: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Feature matching metrics (for ML training relevance)
    feature_match_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    geometric_alignment_error: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Temporal difference
    capture_date_diff_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("tile_a_id", "tile_b_id", name="uq_tile_comparison"),
        Index("idx_comparison_tiles", "tile_a_id", "tile_b_id"),
    )
