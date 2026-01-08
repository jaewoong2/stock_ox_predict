-- Rollback: remove crypto range prediction extensions

DROP INDEX IF EXISTS ix_predictions_crypto_settlement;
DROP INDEX IF EXISTS uq_predictions_range;
DROP INDEX IF EXISTS uq_predictions_direction;

ALTER TABLE crypto.predictions
    DROP CONSTRAINT IF EXISTS predictions_prediction_type_check;

ALTER TABLE crypto.predictions
    ALTER COLUMN choice SET NOT NULL;

ALTER TABLE crypto.predictions
    DROP COLUMN IF EXISTS settlement_price;

ALTER TABLE crypto.predictions
    DROP COLUMN IF EXISTS target_close_time_ms;

ALTER TABLE crypto.predictions
    DROP COLUMN IF EXISTS target_open_time_ms;

ALTER TABLE crypto.predictions
    DROP COLUMN IF EXISTS price_high;

ALTER TABLE crypto.predictions
    DROP COLUMN IF EXISTS price_low;

ALTER TABLE crypto.predictions
    DROP COLUMN IF EXISTS prediction_type;

ALTER TABLE crypto.predictions
    ADD CONSTRAINT predictions_trading_day_user_id_symbol_key
    UNIQUE (trading_day, user_id, symbol);
