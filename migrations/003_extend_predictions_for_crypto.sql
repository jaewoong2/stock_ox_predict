-- Extend predictions table to support crypto range predictions

ALTER TABLE crypto.predictions
    ADD COLUMN IF NOT EXISTS prediction_type VARCHAR(20) NOT NULL DEFAULT 'DIRECTION';

ALTER TABLE crypto.predictions
    DROP CONSTRAINT IF EXISTS predictions_prediction_type_check;

ALTER TABLE crypto.predictions
    ADD CONSTRAINT predictions_prediction_type_check
    CHECK (prediction_type IN ('DIRECTION', 'RANGE'));

ALTER TABLE crypto.predictions
    ADD COLUMN IF NOT EXISTS price_low NUMERIC(20, 8);

ALTER TABLE crypto.predictions
    ADD COLUMN IF NOT EXISTS price_high NUMERIC(20, 8);

ALTER TABLE crypto.predictions
    ADD COLUMN IF NOT EXISTS target_open_time_ms BIGINT;

ALTER TABLE crypto.predictions
    ADD COLUMN IF NOT EXISTS target_close_time_ms BIGINT;

ALTER TABLE crypto.predictions
    ADD COLUMN IF NOT EXISTS settlement_price NUMERIC(20, 8);

ALTER TABLE crypto.predictions
    ALTER COLUMN choice DROP NOT NULL;

ALTER TABLE crypto.predictions
    DROP CONSTRAINT IF EXISTS predictions_trading_day_user_id_symbol_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_predictions_direction
    ON crypto.predictions (trading_day, user_id, symbol, prediction_type)
    WHERE prediction_type = 'DIRECTION';

CREATE UNIQUE INDEX IF NOT EXISTS uq_predictions_range
    ON crypto.predictions (user_id, target_open_time_ms, prediction_type)
    WHERE prediction_type = 'RANGE';

CREATE INDEX IF NOT EXISTS ix_predictions_crypto_settlement
    ON crypto.predictions (target_open_time_ms, status)
    WHERE prediction_type = 'RANGE';
