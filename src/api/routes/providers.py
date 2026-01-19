"""Provider management routes."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.config import settings
from src.db import get_db
from src.db.models import Provider, ProviderName
from src.providers import get_all_providers, get_provider

router = APIRouter()


class ProviderResponse(BaseModel):
    """Provider info response."""

    name: str
    display_name: str
    max_zoom: int
    requires_api_key: bool
    api_key_configured: bool
    enabled: bool


class ProviderListResponse(BaseModel):
    """List of providers response."""

    providers: list[ProviderResponse]


@router.get("", response_model=ProviderListResponse)
async def list_providers():
    """List all available tile providers."""
    providers = get_all_providers()

    result = []
    for name, provider in providers.items():
        api_key_configured = True
        if provider.requires_api_key:
            if name == ProviderName.GOOGLE:
                api_key_configured = bool(settings.google_maps_api_key)
            elif name == ProviderName.BING:
                api_key_configured = bool(settings.bing_maps_api_key)
            elif name == ProviderName.MAPBOX:
                api_key_configured = bool(settings.mapbox_access_token)

        result.append(
            ProviderResponse(
                name=name.value,
                display_name=provider.display_name,
                max_zoom=provider.max_zoom,
                requires_api_key=provider.requires_api_key,
                api_key_configured=api_key_configured,
                enabled=not provider.requires_api_key or api_key_configured,
            )
        )

    return ProviderListResponse(providers=result)


@router.get("/{provider_name}", response_model=ProviderResponse)
async def get_provider_info(provider_name: str):
    """Get info about a specific provider."""
    try:
        name = ProviderName(provider_name)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider_name}")

    provider = get_provider(name)

    api_key_configured = True
    if provider.requires_api_key:
        if name == ProviderName.GOOGLE:
            api_key_configured = bool(settings.google_maps_api_key)
        elif name == ProviderName.BING:
            api_key_configured = bool(settings.bing_maps_api_key)
        elif name == ProviderName.MAPBOX:
            api_key_configured = bool(settings.mapbox_access_token)

    return ProviderResponse(
        name=name.value,
        display_name=provider.display_name,
        max_zoom=provider.max_zoom,
        requires_api_key=provider.requires_api_key,
        api_key_configured=api_key_configured,
        enabled=not provider.requires_api_key or api_key_configured,
    )


@router.get("/{provider_name}/preview")
async def get_tile_preview(
    provider_name: str,
    lat: float,
    lon: float,
    zoom: int = 15,
):
    """Get a preview tile URL for given coordinates."""
    try:
        name = ProviderName(provider_name)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider_name}")

    provider = get_provider(name)
    x, y = provider.coords_to_tile(lon, lat, zoom)

    return {
        "provider": provider_name,
        "tile_x": x,
        "tile_y": y,
        "zoom": zoom,
        "url": provider.get_tile_url(x, y, zoom),
        "bounds": provider.tile_to_bounds(x, y, zoom),
        "gsd_meters": provider.calculate_gsd(lat, zoom),
    }
