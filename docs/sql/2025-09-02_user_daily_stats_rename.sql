-- Rename column max_predictions -> available_predictions in crypto.user_daily_stats
ALTER TABLE crypto.user_daily_stats
  RENAME COLUMN max_predictions TO available_predictions;

-- Optional: update dependent indexes or constraints if any were named
-- (none expected based on current model)

-- Backfill or data adjustment is not required since it's a pure rename

