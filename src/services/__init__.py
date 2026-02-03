"""Services module."""

from src.services.tile_manager import TileManager
from src.services.comparator import TileComparator
from src.services.http_client import (
    TileCache,
    RequestDeduplicator,
    HTTPClientManager,
    get_tile_cache,
    get_request_deduplicator,
    get_http_client_manager,
    cleanup,
)

__all__ = [
    "TileManager",
    "TileComparator",
    "TileCache",
    "RequestDeduplicator",
    "HTTPClientManager",
    "get_tile_cache",
    "get_request_deduplicator",
    "get_http_client_manager",
    "cleanup",
]
