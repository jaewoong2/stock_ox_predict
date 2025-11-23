-- Migration: Create user_favorites table
-- Description: Junction table for many-to-many relationship between users and tickers
-- Created: 2025-11-21
-- Author: Claude Code

-- Create user_favorites table
CREATE TABLE IF NOT EXISTS crypto.user_favorites (
    user_id BIGINT NOT NULL,
    symbol VARCHAR NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Composite primary key: one user can favorite many tickers, no duplicates
    CONSTRAINT pk_user_favorites PRIMARY KEY (user_id, symbol),

    -- Foreign key to users table (cascade delete if user is deleted)
    CONSTRAINT fk_user_favorites_user_id
        FOREIGN KEY (user_id)
        REFERENCES crypto.users(id)
        ON DELETE CASCADE,

    -- Foreign key to tickers_reference table (cascade delete if ticker is removed)
    CONSTRAINT fk_user_favorites_symbol
        FOREIGN KEY (symbol)
        REFERENCES crypto.tickers_reference(symbol)
        ON DELETE CASCADE
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_user_favorites_user_id
    ON crypto.user_favorites(user_id);

CREATE INDEX IF NOT EXISTS idx_user_favorites_symbol
    ON crypto.user_favorites(symbol);

CREATE INDEX IF NOT EXISTS idx_user_favorites_created_at
    ON crypto.user_favorites(created_at DESC);

-- Add comment to table
COMMENT ON TABLE crypto.user_favorites IS
    'User favorite tickers/stocks watchlist. Junction table for many-to-many relationship.';

COMMENT ON COLUMN crypto.user_favorites.user_id IS
    'Reference to user who favorited the ticker';

COMMENT ON COLUMN crypto.user_favorites.symbol IS
    'Stock ticker symbol (e.g., AAPL, GOOGL)';

COMMENT ON COLUMN crypto.user_favorites.created_at IS
    'Timestamp when the favorite was added';

COMMENT ON COLUMN crypto.user_favorites.updated_at IS
    'Timestamp when the record was last updated';
