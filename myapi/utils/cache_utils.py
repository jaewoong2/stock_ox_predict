"""
Cache key generation and TTL calculation utilities.
Key Format: binance:klines:{symbol}:{interval}:{limit}:{start}:{end}
"""

from datetime import datetime
from typing import Optional
import pytz


def generate_klines_cache_key(
    symbol: str,
    interval: str,
    limit: int,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
) -> str:
    """Generate deterministic cache key from request parameters"""
    start_str = str(start_time) if start_time is not None else "none"
    end_str = str(end_time) if end_time is not None else "none"

    key = f"binance:klines:{symbol.upper()}:{interval}:{limit}:{start_str}:{end_str}"
    return key


def calculate_hour_aligned_ttl() -> int:
    """
    Calculate seconds until next hour boundary (Asia/Seoul timezone).

    Examples:
        14:23:45 KST → 2175 seconds (until 15:00:00)
        14:59:50 KST → 10 seconds (until 15:00:00)
        15:00:00 KST → 3600 seconds (until 16:00:00)

    Returns:
        TTL in seconds (1-3600)
    """
    kst_tz = pytz.timezone("Asia/Seoul")
    now_kst = datetime.now(kst_tz)

    current_minute = now_kst.minute
    current_second = now_kst.second

    # Seconds until next hour = (60 - minutes) * 60 - seconds
    seconds_to_next_hour = (60 - current_minute) * 60 - current_second

    # Edge case: if exactly on the hour or calculation error
    if seconds_to_next_hour <= 0:
        return 3600

    return seconds_to_next_hour
