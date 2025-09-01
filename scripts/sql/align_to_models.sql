-- Align DB schema to match SQLAlchemy models (raw SQL)
-- Target schema: crypto
-- Safe to run multiple times (idempotent-ish); includes backups for major change.

BEGIN;

-- 0) Ensure target schema exists
CREATE SCHEMA IF NOT EXISTS crypto;

-- 1) Ensure UUID generation available (for new eod_prices.id)
CREATE EXTENSION IF NOT EXISTS pgcrypto; -- provides gen_random_uuid()

-- 2) Create missing table: crypto.error_logs
CREATE TABLE IF NOT EXISTS crypto.error_logs (
  id BIGSERIAL PRIMARY KEY,
  check_type TEXT NOT NULL,
  trading_day DATE,
  status TEXT NOT NULL DEFAULT 'FAILED',
  details JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 3) Standardize TIMESTAMP columns to TIMESTAMPTZ (timezone-aware)
-- Convert only when current type is timestamp without time zone
DO $$
DECLARE
  r record;
BEGIN
  FOR r IN
    SELECT table_schema, table_name, column_name
    FROM information_schema.columns
    WHERE table_schema = 'crypto'
      AND data_type = 'timestamp without time zone'
      AND (table_name, column_name) IN (
        -- session_control
        ('session_control','predict_open_at'),
        ('session_control','predict_cutoff_at'),
        ('session_control','settle_ready_at'),
        ('session_control','settled_at'),
        ('session_control','created_at'),
        ('session_control','updated_at'),
        -- users
        ('users','last_login_at'),
        ('users','created_at'),
        ('users','updated_at'),
        -- active_universe
        ('active_universe','created_at'),
        ('active_universe','updated_at'),
        -- settlements
        ('settlements','computed_at'),
        ('settlements','created_at'),
        ('settlements','updated_at'),
        -- oauth_states
        ('oauth_states','expires_at'),
        ('oauth_states','created_at'),
        ('oauth_states','updated_at'),
        -- eod_prices
        ('eod_prices','fetched_at'),
        ('eod_prices','created_at'),
        ('eod_prices','updated_at'),
        -- ad_unlocks
        ('ad_unlocks','created_at'),
        ('ad_unlocks','updated_at'),
        -- points_ledger
        ('points_ledger','created_at'),
        ('points_ledger','updated_at'),
        -- predictions
        ('predictions','submitted_at'),
        ('predictions','updated_at'),
        ('predictions','locked_at'),
        ('predictions','created_at'),
        -- rewards
        ('rewards_inventory','created_at'),
        ('rewards_inventory','updated_at'),
        ('rewards_redemptions','created_at'),
        ('rewards_redemptions','updated_at'),
        -- user_daily_stats
        ('user_daily_stats','created_at'),
        ('user_daily_stats','updated_at')
      )
  LOOP
    EXECUTE format(
      'ALTER TABLE %I.%I ALTER COLUMN %I TYPE timestamptz USING %I AT TIME ZONE ''UTC''',
      r.table_schema, r.table_name, r.column_name, r.column_name
    );
  END LOOP;
END$$;

-- 4) Normalize oauth_states text->varchar (no length)
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='crypto' AND table_name='oauth_states' AND column_name='state' AND data_type='text'
  ) THEN
    ALTER TABLE crypto.oauth_states ALTER COLUMN state TYPE varchar;
  END IF;
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='crypto' AND table_name='oauth_states' AND column_name='redirect_uri' AND data_type='text'
  ) THEN
    ALTER TABLE crypto.oauth_states ALTER COLUMN redirect_uri TYPE varchar;
  END IF;
END$$;

-- 5) Rebuild eod_prices to match models (UUID PK, varchar(10) symbol, computed fields)
-- Create new table if current id is not UUID
DO $$
DECLARE
  is_uuid boolean;
BEGIN
  SELECT (data_type='uuid') INTO is_uuid
  FROM information_schema.columns
  WHERE table_schema='crypto' AND table_name='eod_prices' AND column_name='id';

  IF NOT COALESCE(is_uuid, false) THEN
    -- Create v2 table with desired schema
    CREATE TABLE IF NOT EXISTS crypto.eod_prices_v2 (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      symbol varchar(10) NOT NULL,
      trading_date date NOT NULL,
      open_price numeric(10,4) NOT NULL,
      high_price numeric(10,4) NOT NULL,
      low_price numeric(10,4) NOT NULL,
      close_price numeric(10,4) NOT NULL,
      adjusted_close numeric(10,4),
      previous_close numeric(10,4) NOT NULL,
      change_amount numeric(10,4) NOT NULL,
      change_percent numeric(6,4) NOT NULL,
      volume integer NOT NULL,
      data_source varchar(50) NOT NULL DEFAULT 'yfinance',
      fetched_at timestamptz NOT NULL DEFAULT now(),
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    );

    -- Create indexes
    CREATE UNIQUE INDEX IF NOT EXISTS ix_eod_prices_symbol_date_v2 ON crypto.eod_prices_v2(symbol, trading_date);
    CREATE INDEX IF NOT EXISTS ix_eod_prices_trading_date_v2 ON crypto.eod_prices_v2(trading_date);
    CREATE INDEX IF NOT EXISTS ix_eod_prices_fetched_at_v2 ON crypto.eod_prices_v2(fetched_at);

    -- Copy data with mapping from old columns if present
    INSERT INTO crypto.eod_prices_v2 (
      symbol, trading_date, open_price, high_price, low_price, close_price,
      adjusted_close, previous_close, change_amount, change_percent, volume,
      data_source, fetched_at, created_at, updated_at
    )
    SELECT
      LEFT(COALESCE(ep.symbol::text, ''), 10) AS symbol,
      COALESCE((ep.asof)::date, (ep.fetched_at)::date, now()::date) AS trading_date,
      ROUND(ep.open_price::numeric, 4) AS open_price,
      ROUND(ep.high_price::numeric, 4) AS high_price,
      ROUND(ep.low_price::numeric, 4) AS low_price,
      ROUND(ep.close_price::numeric, 4) AS close_price,
      NULL::numeric(10,4) AS adjusted_close,
      ROUND(COALESCE(ep.prev_close_price::numeric, ep.close_price::numeric), 4) AS previous_close,
      ROUND(ep.close_price::numeric - COALESCE(ep.prev_close_price::numeric, ep.close_price::numeric), 4) AS change_amount,
      ROUND(
        CASE WHEN COALESCE(ep.prev_close_price::numeric, 0) <> 0
          THEN ((ep.close_price::numeric - ep.prev_close_price::numeric) / ep.prev_close_price::numeric) * 100
          ELSE 0
        END, 4
      ) AS change_percent,
      LEAST(COALESCE(ep.volume::bigint, 0), 2147483647)::integer AS volume,
      COALESCE(NULLIF(ep.vendor_rev::text, ''), 'yfinance') AS data_source,
      (COALESCE(ep.fetched_at, ep.asof, now()))::timestamptz AS fetched_at,
      COALESCE(ep.created_at, now())::timestamptz AS created_at,
      COALESCE(ep.updated_at, now())::timestamptz AS updated_at
    FROM crypto.eod_prices ep
    ON CONFLICT DO NOTHING;

    -- Swap tables: keep backup as eod_prices_old
    ALTER TABLE crypto.eod_prices RENAME TO eod_prices_old;
    ALTER TABLE crypto.eod_prices_v2 RENAME TO eod_prices;

    -- Recreate expected indexes with final names
    IF NOT EXISTS (
      SELECT 1 FROM pg_indexes WHERE schemaname='crypto' AND indexname='ix_eod_prices_symbol_date'
    ) THEN
      CREATE UNIQUE INDEX ix_eod_prices_symbol_date ON crypto.eod_prices(symbol, trading_date);
    END IF;
    IF NOT EXISTS (
      SELECT 1 FROM pg_indexes WHERE schemaname='crypto' AND indexname='ix_eod_prices_trading_date'
    ) THEN
      CREATE INDEX ix_eod_prices_trading_date ON crypto.eod_prices(trading_date);
    END IF;
    IF NOT EXISTS (
      SELECT 1 FROM pg_indexes WHERE schemaname='crypto' AND indexname='ix_eod_prices_fetched_at'
    ) THEN
      CREATE INDEX ix_eod_prices_fetched_at ON crypto.eod_prices(fetched_at);
    END IF;
  END IF;
END$$;

COMMIT;

-- Notes:
-- - Extra tables listed by the checker are left untouched.
-- - Review eod_prices_old and drop it after validation if not needed.
-- - Consider adding NOT NULL/DEFAULTs or triggers for updated_at if desired.
