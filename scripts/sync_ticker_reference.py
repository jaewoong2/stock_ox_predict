"""
Sync ticker reference data from active_universe.

This script:
1. Finds symbols in active_universe that are missing from tickers_reference
2. Fetches ticker details from Polygon.io API
3. Inserts missing ticker data into tickers_reference
"""

import os
import sys
from datetime import datetime, timezone
from typing import List, Set

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from myapi.database.session import get_db
from myapi.models.session import ActiveUniverse
from myapi.models.ticker_reference import TickerReference
from myapi.config import settings
import requests


def get_missing_symbols(db) -> Set[str]:
    """Find symbols in active_universe that are missing from tickers_reference."""
    # Get all unique symbols from active_universe
    universe_symbols = db.execute(
        select(ActiveUniverse.symbol).distinct()
    ).scalars().all()

    # Get all symbols from tickers_reference
    reference_symbols = db.execute(
        select(TickerReference.symbol)
    ).scalars().all()

    universe_set = set(universe_symbols)
    reference_set = set(reference_symbols)

    # Find missing symbols
    missing_symbols = universe_set - reference_set

    print(f"\n📊 Summary:")
    print(f"  • Total symbols in active_universe: {len(universe_set)}")
    print(f"  • Total symbols in tickers_reference: {len(reference_set)}")
    print(f"  • Missing symbols: {len(missing_symbols)}")

    return missing_symbols


def fetch_ticker_details(symbol: str, api_key: str) -> dict:
    """Fetch ticker details from Polygon.io API."""
    url = f"https://api.polygon.io/v3/reference/tickers/{symbol}"
    params = {"apiKey": api_key}

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get("status") == "OK" and "results" in data:
            results = data["results"]
            return {
                "symbol": symbol,
                "name": results.get("name", symbol),
                "market_category": results.get("market", None),
                "is_etf": results.get("type") == "ETF",
                "exchange": results.get("primary_exchange", None),
            }
        else:
            print(f"  ⚠️  {symbol}: API returned non-OK status")
            return None

    except requests.exceptions.RequestException as e:
        print(f"  ❌ {symbol}: API request failed - {e}")
        return None
    except Exception as e:
        print(f"  ❌ {symbol}: Unexpected error - {e}")
        return None


def insert_ticker_reference(db, ticker_data: dict) -> bool:
    """Insert ticker data into tickers_reference table."""
    try:
        ticker = TickerReference(
            symbol=ticker_data["symbol"],
            name=ticker_data["name"],
            market_category=ticker_data.get("market_category"),
            is_etf=ticker_data.get("is_etf", False),
            exchange=ticker_data.get("exchange"),
            ingested_at_utc=datetime.now(timezone.utc),
        )

        db.add(ticker)
        db.commit()
        return True

    except Exception as e:
        db.rollback()
        print(f"  ❌ Failed to insert {ticker_data['symbol']}: {e}")
        return False


def main():
    """Main execution function."""
    print("=" * 70)
    print("🔄 Syncing Ticker Reference Data")
    print("=" * 70)

    # Get database session
    db = next(get_db())

    try:
        # Step 1: Find missing symbols
        print("\n📋 Step 1: Finding missing symbols...")
        missing_symbols = get_missing_symbols(db)

        if not missing_symbols:
            print("\n✅ No missing symbols found. All symbols are synced!")
            return

        print(f"\n🔍 Missing symbols ({len(missing_symbols)}):")
        for symbol in sorted(missing_symbols):
            print(f"  • {symbol}")

        # Auto-proceed (can add --confirm flag if needed)
        print("\n" + "=" * 70)
        print(f"\n✅ Proceeding to fetch and insert {len(missing_symbols)} ticker(s)...")

        # Check for API key
        polygon_api_key = os.getenv("POLYGON_API_KEY") or getattr(settings, "POLYGON_API_KEY", None)

        if not polygon_api_key:
            print("\n⚠️  POLYGON_API_KEY not found - will create fallback entries only")
            print("   (Symbol will be used as name)")
            use_api = False
        else:
            print(f"\n✅ Found POLYGON_API_KEY - will fetch from Polygon.io API")
            use_api = True

        # Step 2: Fetch and insert missing tickers
        print(f"\n📥 Step 2: Fetching ticker details from Polygon.io...")
        print("=" * 70)

        success_count = 0
        failed_count = 0

        for i, symbol in enumerate(sorted(missing_symbols), 1):
            print(f"\n[{i}/{len(missing_symbols)}] Processing {symbol}...")

            ticker_data = None

            # Try to fetch from API if available
            if use_api:
                ticker_data = fetch_ticker_details(symbol, polygon_api_key)

            if ticker_data:
                # Insert into database with API data
                if insert_ticker_reference(db, ticker_data):
                    print(f"  ✅ {symbol}: Successfully inserted (from API)")
                    success_count += 1
                else:
                    failed_count += 1
            else:
                # Create fallback entry with minimal data
                if use_api:
                    print(f"  ⚠️  {symbol}: API fetch failed, creating fallback entry...")
                else:
                    print(f"  ℹ️  {symbol}: Creating fallback entry...")

                fallback_data = {
                    "symbol": symbol,
                    "name": symbol,  # Use symbol as name
                    "market_category": None,
                    "is_etf": False,
                    "exchange": None,
                }

                if insert_ticker_reference(db, fallback_data):
                    print(f"  ✅ {symbol}: Fallback entry created")
                    success_count += 1
                else:
                    failed_count += 1

        # Summary
        print("\n" + "=" * 70)
        print("📊 Final Summary:")
        print(f"  ✅ Successfully inserted: {success_count}")
        print(f"  ❌ Failed: {failed_count}")
        print(f"  📈 Total processed: {len(missing_symbols)}")
        print("=" * 70)

        if success_count > 0:
            print("\n🎉 Ticker reference sync completed!")

    finally:
        db.close()


if __name__ == "__main__":
    main()
