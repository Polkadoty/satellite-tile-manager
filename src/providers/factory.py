"""Factory for creating tile provider instances."""

from src.config import settings
from src.db.models import ProviderName
from src.providers.base import TileProvider
from src.providers.bing import BingMapsProvider
from src.providers.google import GoogleMapsProvider
from src.providers.mapbox import MapboxProvider
from src.providers.naip import NAIPProvider


_PROVIDER_CLASSES: dict[ProviderName, type[TileProvider]] = {
    ProviderName.NAIP: NAIPProvider,
    ProviderName.GOOGLE: GoogleMapsProvider,
    ProviderName.BING: BingMapsProvider,
    ProviderName.MAPBOX: MapboxProvider,
}

_provider_instances: dict[ProviderName, TileProvider] = {}


def get_provider(name: ProviderName) -> TileProvider:
    """Get a tile provider instance by name.

    Args:
        name: Provider name enum

    Returns:
        TileProvider instance

    Raises:
        ValueError: If provider is not supported
    """
    if name not in _PROVIDER_CLASSES:
        raise ValueError(f"Unknown provider: {name}")

    # Return cached instance if available
    if name in _provider_instances:
        return _provider_instances[name]

    # Create new instance
    provider = _PROVIDER_CLASSES[name]()
    _provider_instances[name] = provider
    return provider


def get_all_providers() -> dict[ProviderName, TileProvider]:
    """Get all available tile providers.

    Returns:
        Dict mapping provider names to instances
    """
    providers = {}
    for name in _PROVIDER_CLASSES:
        providers[name] = get_provider(name)
    return providers


def get_enabled_providers() -> dict[ProviderName, TileProvider]:
    """Get all enabled tile providers (those with API keys configured).

    Returns:
        Dict mapping provider names to instances
    """
    providers = {}

    for name, cls in _PROVIDER_CLASSES.items():
        provider = get_provider(name)

        # Check if API key is required and configured
        if provider.requires_api_key:
            if name == ProviderName.GOOGLE and not settings.google_maps_api_key:
                continue
            if name == ProviderName.BING and not settings.bing_maps_api_key:
                continue
            if name == ProviderName.MAPBOX and not settings.mapbox_access_token:
                continue

        providers[name] = provider

    return providers
