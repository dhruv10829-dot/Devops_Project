"""
Redis Caching Layer for CI/CD Prediction Results
Caches predictions to reduce redundant computations
"""

import os
import json
import hashlib
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis not available. Install with: pip install redis")


class PredictionCache:
    """Redis-based cache for prediction results"""

    def __init__(self):
        """Initialize Redis connection"""
        if not REDIS_AVAILABLE:
            self.redis_client = None
            logger.info("Redis caching disabled (redis package not installed)")
            return

        redis_host = os.getenv('REDIS_HOST', 'localhost')
        redis_port = int(os.getenv('REDIS_PORT', 6379))
        redis_password = os.getenv('REDIS_PASSWORD')
        enable_cache = os.getenv('ENABLE_CACHE', 'true').lower() == 'true'

        if not enable_cache:
            self.redis_client = None
            logger.info("Redis caching disabled via ENABLE_CACHE")
            return

        try:
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                password=redis_password,
                db=0,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )
            # Test connection
            self.redis_client.ping()
            logger.info(f"✅ Redis cache connected: {redis_host}:{redis_port}")
        except Exception as e:
            self.redis_client = None
            logger.warning(f"Failed to connect to Redis: {e}")

    def is_available(self) -> bool:
        """Check if Redis cache is available"""
        if self.redis_client is None:
            return False
        try:
            self.redis_client.ping()
            return True
        except Exception:
            return False

    def _generate_cache_key(self, input_data: Dict[str, Any]) -> str:
        """Generate a unique cache key from input data"""
        # Sort keys for consistent hashing
        sorted_data = json.dumps(input_data, sort_keys=True)
        data_hash = hashlib.sha256(sorted_data.encode()).hexdigest()
        return f"prediction:{data_hash}"

    def get(self, input_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get cached prediction result"""
        if not self.is_available():
            return None

        cache_key = self._generate_cache_key(input_data)

        try:
            cached = self.redis_client.get(cache_key)
            if cached:
                logger.debug(f"Cache HIT: {cache_key[:16]}...")
                return json.loads(cached)
            logger.debug(f"Cache MISS: {cache_key[:16]}...")
            return None
        except Exception as e:
            logger.warning(f"Cache get error: {e}")
            return None

    def set(self, input_data: Dict[str, Any], result: Dict[str, Any], ttl: int = 3600):
        """Cache prediction result with TTL (default 1 hour)"""
        if not self.is_available():
            return

        cache_key = self._generate_cache_key(input_data)

        try:
            self.redis_client.setex(
                cache_key,
                ttl,
                json.dumps(result)
            )
            logger.debug(f"Cached result: {cache_key[:16]}... (TTL: {ttl}s)")
        except Exception as e:
            logger.warning(f"Cache set error: {e}")

    def delete(self, input_data: Dict[str, Any]) -> bool:
        """Delete cached prediction result"""
        if not self.is_available():
            return False

        cache_key = self._generate_cache_key(input_data)

        try:
            self.redis_client.delete(cache_key)
            logger.debug(f"Deleted cache: {cache_key[:16]}...")
            return True
        except Exception as e:
            logger.warning(f"Cache delete error: {e}")
            return False

    def clear_all(self) -> bool:
        """Clear all prediction caches"""
        if not self.is_available():
            return False

        try:
            keys = self.redis_client.keys("prediction:*")
            if keys:
                self.redis_client.delete(*keys)
                logger.info(f"Cleared {len(keys)} cached predictions")
            return True
        except Exception as e:
            logger.warning(f"Cache clear error: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        if not self.is_available():
            return {"available": False}

        try:
            info = self.redis_client.info('stats')
            keyspace = self.redis_client.info('keyspace')
            prediction_keys = len(self.redis_client.keys("prediction:*"))

            return {
                "available": True,
                "total_keys": prediction_keys,
                "hits": info.get('keyspace_hits', 0),
                "misses": info.get('keyspace_misses', 0),
                "hit_rate": info.get('keyspace_hits', 0) / max(
                    info.get('keyspace_hits', 0) + info.get('keyspace_misses', 0), 1
                ),
                "db_size": self.redis_client.dbsize()
            }
        except Exception as e:
            logger.warning(f"Cache stats error: {e}")
            return {"available": True, "error": str(e)}


# Global cache instance
_cache_instance = None


def get_cache() -> PredictionCache:
    """Get or create the global cache instance"""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = PredictionCache()
    return _cache_instance
