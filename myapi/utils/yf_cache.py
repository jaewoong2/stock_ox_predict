from __future__ import annotations

import os
from typing import Optional

import yfinance as yf


def configure_yfinance_cache(explicit_dir: Optional[str] = None) -> str:
    """Configure yfinance caches to a writable directory.

    Priority for base cache location:
    1) explicit_dir (if provided)
    2) env YFINANCE_CACHE_DIR
    3) env MPLCONFIGDIR (common in Lambda setups)
    4) env TMPDIR
    5) '/tmp' when running on Lambda (AWS_LAMBDA_FUNCTION_NAME present)
    6) '/tmp' as safe default

    Also sets MPLCONFIGDIR to the chosen base dir when running on Lambda and
    MPLCONFIGDIR is not already set, to mirror previous patterns.
    """
    # Resolve base directory
    base_dir = (
        explicit_dir
        or os.environ.get("YFINANCE_CACHE_DIR")
        or os.environ.get("MPLCONFIGDIR")
        or os.environ.get("TMPDIR")
    )

    if not base_dir:
        # If on Lambda, prefer /tmp which is writable
        if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
            base_dir = "/tmp"
        else:
            base_dir = "/tmp"

    # Ensure directory exists
    cache_dir = os.path.join(base_dir, "py-yfinance")
    try:
        os.makedirs(cache_dir, exist_ok=True)
    except Exception:
        # As a last resort, use /tmp directly
        cache_dir = "/tmp/py-yfinance"
        try:
            os.makedirs(cache_dir, exist_ok=True)
        except Exception:
            # Give up; yfinance will proceed without caches
            return cache_dir

    # Configure yfinance caches if supported by version
    try:
        if hasattr(yf, "set_tz_cache_location"):
            yf.set_tz_cache_location(cache_dir)  # type: ignore[attr-defined]
        if hasattr(yf, "set_cookie_cache_location"):
            yf.set_cookie_cache_location(cache_dir)  # type: ignore[attr-defined]
    except Exception:
        # Non-fatal; just skip configuration
        pass

    # Mirror historical pattern: ensure MPLCONFIGDIR points to a writable dir on Lambda
    if os.environ.get("AWS_LAMBDA_FUNCTION_NAME") and not os.environ.get(
        "MPLCONFIGDIR"
    ):
        try:
            os.environ["MPLCONFIGDIR"] = base_dir
        except Exception:
            pass

    return cache_dir

