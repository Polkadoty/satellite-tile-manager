"""Shared HTTP client manager with connection pooling and optimization."""

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
import hashlib

import httpx

from src.config import settings


@dataclass
class CacheEntry:
    """Cache entry for tile data."""
    data: bytes
    content_type: str
    created_at: datetime
    size: int
    hits: int = 0


class TileCache:
    """In-memory LRU cache for tile data.

    Provides fast access to recently downloaded tiles without hitting disk.
    Useful for repeated access patterns and tile comparison workflows.
    """

    def __init__(self, max_size_mb: int = 100, max_entries: int = 1000, ttl_seconds: int = 3600):
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.max_entries = max_entries
        self.ttl = timedelta(seconds=ttl_seconds)
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._current_size = 0
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    def _make_key(self, provider: str, x: int, y: int, zoom: int) -> str:
        """Create cache key from tile coordinates."""
        return f"{provider}:{zoom}:{x}:{y}"

    async def get(self, provider: str, x: int, y: int, zoom: int) -> Optional[bytes]:
        """Get tile data from cache if available."""
        key = self._make_key(provider, x, y, zoom)

        async with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                # Check TTL
                if datetime.utcnow() - entry.created_at > self.ttl:
                    self._remove_entry(key)
                    self._misses += 1
                    return None

                # Move to end (LRU)
                self._cache.move_to_end(key)
                entry.hits += 1
                self._hits += 1
                return entry.data

            self._misses += 1
            return None

    async def put(self, provider: str, x: int, y: int, zoom: int, data: bytes, content_type: str = "image/png"):
        """Store tile data in cache."""
        key = self._make_key(provider, x, y, zoom)
        size = len(data)

        async with self._lock:
            # Remove existing entry if present
            if key in self._cache:
                self._remove_entry(key)

            # Evict entries if needed
            while self._current_size + size > self.max_size_bytes or len(self._cache) >= self.max_entries:
                if not self._cache:
                    break
                # Remove oldest (first) entry
                oldest_key = next(iter(self._cache))
                self._remove_entry(oldest_key)

            # Add new entry
            self._cache[key] = CacheEntry(
                data=data,
                content_type=content_type,
                created_at=datetime.utcnow(),
                size=size,
            )
            self._current_size += size

    def _remove_entry(self, key: str):
        """Remove entry from cache."""
        if key in self._cache:
            self._current_size -= self._cache[key].size
            del self._cache[key]

    async def clear(self):
        """Clear all cache entries."""
        async with self._lock:
            self._cache.clear()
            self._current_size = 0

    def stats(self) -> dict:
        """Get cache statistics."""
        total_requests = self._hits + self._misses
        return {
            "entries": len(self._cache),
            "size_mb": round(self._current_size / (1024 * 1024), 2),
            "max_size_mb": self.max_size_bytes // (1024 * 1024),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total_requests * 100, 2) if total_requests > 0 else 0,
        }


class RequestDeduplicator:
    """Prevents duplicate concurrent requests for the same tile.

    When multiple requests come in for the same tile simultaneously,
    only one actual download is performed and all waiters receive the result.
    """

    def __init__(self):
        self._pending: dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    def _make_key(self, provider: str, x: int, y: int, zoom: int) -> str:
        """Create unique key for request."""
        return f"{provider}:{zoom}:{x}:{y}"

    async def get_or_fetch(
        self,
        provider: str,
        x: int,
        y: int,
        zoom: int,
        fetch_func,
    ):
        """Get result from pending request or initiate new fetch.

        Args:
            provider: Provider name
            x, y, zoom: Tile coordinates
            fetch_func: Async function to call if no pending request exists

        Returns:
            Result from fetch_func
        """
        key = self._make_key(provider, x, y, zoom)

        async with self._lock:
            if key in self._pending:
                # Wait for existing request
                future = self._pending[key]
            else:
                # Create new request
                future = asyncio.get_event_loop().create_future()
                self._pending[key] = future

                # Start fetch in background
                asyncio.create_task(self._do_fetch(key, future, fetch_func))

        # Wait for result
        return await future

    async def _do_fetch(self, key: str, future: asyncio.Future, fetch_func):
        """Execute fetch and resolve future."""
        try:
            result = await fetch_func()
            future.set_result(result)
        except Exception as e:
            future.set_exception(e)
        finally:
            async with self._lock:
                self._pending.pop(key, None)


class HTTPClientManager:
    """Manages shared HTTP clients with connection pooling.

    Provides optimized clients for each provider with appropriate
    limits, timeouts, and connection reuse.
    """

    def __init__(
        self,
        max_connections: int = 100,
        max_connections_per_host: int = 10,
        timeout_seconds: int = 30,
        keepalive_expiry: int = 30,
    ):
        self.max_connections = max_connections
        self.max_connections_per_host = max_connections_per_host
        self.timeout = httpx.Timeout(timeout_seconds, connect=10.0)
        self.keepalive_expiry = keepalive_expiry
        self._clients: dict[str, httpx.AsyncClient] = {}
        self._lock = asyncio.Lock()

        # Connection limits
        self.limits = httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=max_connections_per_host,
            keepalive_expiry=keepalive_expiry,
        )

    async def get_client(self, provider: str = "default") -> httpx.AsyncClient:
        """Get or create HTTP client for provider."""
        async with self._lock:
            if provider not in self._clients:
                self._clients[provider] = httpx.AsyncClient(
                    timeout=self.timeout,
                    limits=self.limits,
                    http2=True,  # Enable HTTP/2 for multiplexing
                    follow_redirects=True,
                )
            return self._clients[provider]

    async def close_all(self):
        """Close all HTTP clients."""
        async with self._lock:
            for client in self._clients.values():
                await client.aclose()
            self._clients.clear()

    async def close_client(self, provider: str):
        """Close specific provider's client."""
        async with self._lock:
            if provider in self._clients:
                await self._clients[provider].aclose()
                del self._clients[provider]


# Global instances
_tile_cache: Optional[TileCache] = None
_request_deduplicator: Optional[RequestDeduplicator] = None
_http_client_manager: Optional[HTTPClientManager] = None


def get_tile_cache() -> TileCache:
    """Get global tile cache instance."""
    global _tile_cache
    if _tile_cache is None:
        _tile_cache = TileCache(
            max_size_mb=100,
            max_entries=1000,
            ttl_seconds=3600,
        )
    return _tile_cache


def get_request_deduplicator() -> RequestDeduplicator:
    """Get global request deduplicator instance."""
    global _request_deduplicator
    if _request_deduplicator is None:
        _request_deduplicator = RequestDeduplicator()
    return _request_deduplicator


def get_http_client_manager() -> HTTPClientManager:
    """Get global HTTP client manager instance."""
    global _http_client_manager
    if _http_client_manager is None:
        _http_client_manager = HTTPClientManager(
            max_connections=settings.max_concurrent_downloads * 10,
            max_connections_per_host=settings.max_concurrent_downloads,
            timeout_seconds=settings.download_timeout_seconds,
        )
    return _http_client_manager


async def cleanup():
    """Cleanup global resources."""
    global _tile_cache, _http_client_manager

    if _tile_cache:
        await _tile_cache.clear()

    if _http_client_manager:
        await _http_client_manager.close_all()
