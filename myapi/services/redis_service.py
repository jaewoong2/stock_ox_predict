"""
Redis service with async operations and graceful error handling.
- Never raises exceptions (returns None/False on failure)
- Lazy connection with health checks
- Automatic JSON serialization/deserialization
"""

from typing import Optional, Any
import redis.asyncio as redis
import json
import logging
from myapi.config import Settings

logger = logging.getLogger(__name__)


class RedisService:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._client: Optional[redis.Redis] = None
        self._logger = logging.getLogger(__name__)

    async def _get_client(self) -> Optional[redis.Redis]:
        """Lazy connection with health check"""
        if self._client is None:
            try:
                # Prepare connection kwargs
                redis_kwargs = {
                    "host": self._settings.REDIS_HOST,
                    "port": self._settings.REDIS_PORT,
                    "db": self._settings.REDIS_DB,
                    "decode_responses": True,
                    "socket_connect_timeout": 5,
                    "socket_keepalive": True,
                    "health_check_interval": 30,
                }

                # Only add password if it's set
                if self._settings.REDIS_PASSWORD:
                    redis_kwargs["password"] = self._settings.REDIS_PASSWORD

                self._client = redis.Redis(**redis_kwargs)
                await self._client.ping()
            except Exception as e:
                self._logger.warning(f"Redis connection failed: {e}")
                self._client = None
        return self._client

    async def get(self, key: str) -> Optional[Any]:
        """Get cached value, returns None if not found or error"""
        try:
            client = await self._get_client()
            if client is None:
                return None
            value = await client.get(key)
            return json.loads(value) if value else None
        except Exception as e:
            self._logger.warning(f"Redis GET failed for {key}: {e}")
            return None

    async def set(self, key: str, value: Any, ttl_seconds: int) -> bool:
        """Set cache with TTL, returns success status"""
        try:
            client = await self._get_client()
            if client is None:
                return False
            serialized = json.dumps(value)
            await client.setex(key, ttl_seconds, serialized)
            return True
        except Exception as e:
            self._logger.warning(f"Redis SET failed for {key}: {e}")
            return False

    async def close(self):
        """Close connection pool on app shutdown"""
        if self._client:
            await self._client.aclose()
