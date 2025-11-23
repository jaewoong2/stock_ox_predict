-- Migration Rollback: Drop user_favorites table
-- Description: Rollback for creating user_favorites table
-- Created: 2025-11-21
-- Author: Claude Code

-- Drop indexes first
DROP INDEX IF EXISTS crypto.idx_user_favorites_created_at;
DROP INDEX IF EXISTS crypto.idx_user_favorites_symbol;
DROP INDEX IF EXISTS crypto.idx_user_favorites_user_id;

-- Drop the table
DROP TABLE IF EXISTS crypto.user_favorites;
