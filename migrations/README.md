# Database Migrations

This directory contains SQL migration scripts for the database schema changes.

## Running Migrations

### Manual Execution

To apply a migration, connect to your PostgreSQL database and run:

```bash
psql -h <host> -U <user> -d <database> -f migrations/001_create_user_favorites_table.sql
```

Or use the database connection from your `.env` file:

```bash
# Extract connection details from .env and run migration
psql "<your-database-url>" -f migrations/001_create_user_favorites_table.sql
```

### Rollback

To rollback a migration:

```bash
psql "<your-database-url>" -f migrations/001_create_user_favorites_table_rollback.sql
```

## Migration Files

### 001_create_user_favorites_table.sql
- **Created**: 2025-11-21
- **Description**: Creates the `user_favorites` junction table for user watchlist functionality
- **Tables Created**: `crypto.user_favorites`
- **Foreign Keys**:
  - `user_id` → `crypto.users.id`
  - `symbol` → `crypto.tickers_reference.symbol`

## Future: Alembic Setup

This project is Alembic-ready (as mentioned in CLAUDE.md). To set up Alembic for automatic migrations:

```bash
# Install alembic
pip install alembic

# Initialize alembic
alembic init alembic

# Configure alembic.ini and env.py with database connection
# Generate migration from models
alembic revision --autogenerate -m "Initial migration"

# Apply migrations
alembic upgrade head
```

Once Alembic is configured, these manual SQL files can be replaced with Alembic's version-controlled migrations.
