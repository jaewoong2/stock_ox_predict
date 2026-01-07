-- Create table for BTC price band predictions
CREATE TABLE IF NOT EXISTS crypto.crypto_band_predictions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES crypto.users(id),
    trading_day DATE NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    interval VARCHAR(10) NOT NULL DEFAULT '1h',
    future_col SMALLINT NOT NULL DEFAULT 0,
    row SMALLINT NOT NULL,
    target_open_time_ms BIGINT NOT NULL,
    target_close_time_ms BIGINT NOT NULL,
    p0 NUMERIC(20, 8) NOT NULL,
    band_pct_low NUMERIC(10, 6),
    band_pct_high NUMERIC(10, 6),
    band_price_low NUMERIC(20, 8),
    band_price_high NUMERIC(20, 8),
    status VARCHAR(10) NOT NULL DEFAULT 'PENDING',
    settlement_price NUMERIC(20, 8),
    settlement_attempts SMALLINT DEFAULT 0,
    last_settlement_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Idempotency on user + target_open_time_ms + row
CREATE UNIQUE INDEX IF NOT EXISTS uq_crypto_band_predictions_user_target_row
    ON crypto.crypto_band_predictions (user_id, target_open_time_ms, row);

-- Settlement lookup index
CREATE INDEX IF NOT EXISTS ix_crypto_band_predictions_close_time
    ON crypto.crypto_band_predictions (target_close_time_ms);
