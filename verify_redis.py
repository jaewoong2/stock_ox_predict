#!/usr/bin/env python3
"""Verify Redis integration with FastAPI settings"""

import asyncio
from myapi.config import settings
from myapi.services.redis_service import RedisService
from myapi.utils.cache_utils import generate_klines_cache_key, calculate_hour_aligned_ttl


async def main():
    print("="*60)
    print("Redis Configuration Verification")
    print("="*60)

    # 1. Check settings
    print(f"\n1. Configuration Settings:")
    print(f"   REDIS_HOST: {settings.REDIS_HOST}")
    print(f"   REDIS_PORT: {settings.REDIS_PORT}")
    print(f"   REDIS_DB: {settings.REDIS_DB}")
    print(f"   REDIS_PASSWORD: {'(not set)' if not settings.REDIS_PASSWORD else '***'}")
    print(f"   REDIS_ENABLED: {settings.REDIS_ENABLED}")

    # 2. Test cache key generation
    print(f"\n2. Cache Key Generation:")
    cache_key = generate_klines_cache_key("BTCUSDT", "1h", 60)
    print(f"   Example key: {cache_key}")

    # 3. Test TTL calculation
    print(f"\n3. TTL Calculation:")
    ttl = calculate_hour_aligned_ttl()
    print(f"   Seconds until next hour: {ttl}")
    print(f"   Minutes until next hour: {ttl // 60}")

    # 4. Test Redis connection
    print(f"\n4. Redis Connection Test:")
    redis_service = RedisService(settings=settings)

    # Test SET
    test_key = "test:verify"
    test_value = {"test": "data", "timestamp": "2025-01-05"}
    success = await redis_service.set(test_key, test_value, 10)

    if success:
        print(f"   ✅ SET operation successful")

        # Test GET
        retrieved = await redis_service.get(test_key)
        if retrieved == test_value:
            print(f"   ✅ GET operation successful")
            print(f"   Retrieved data: {retrieved}")
        else:
            print(f"   ❌ GET operation failed - data mismatch")
    else:
        print(f"   ❌ SET operation failed")

    # Close connection
    await redis_service.close()

    print("\n" + "="*60)
    print("✅ Verification Complete!")
    print("="*60)
    print("\nNext steps:")
    print("1. Run: uvicorn myapi.main:app --host 0.0.0.0 --port 8000 --reload")
    print("2. Test endpoint: curl 'http://localhost:8000/api/v1/binance/klines?symbol=BTCUSDT&interval=1h&limit=60'")
    print("3. Check logs for 'Cache MISS' then 'Cache HIT' on second request")


if __name__ == "__main__":
    asyncio.run(main())
