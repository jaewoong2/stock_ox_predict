# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Application
```bash
# Local development with uvicorn
uvicorn myapi.main:app --host 0.0.0.0 --port 8000 --reload

# Docker development
docker-compose up --build

# AWS Lambda deployment
./deploy.sh
```

### Testing
```bash
# Run tests (pytest should be used based on test structure)
python -m pytest tests/

# Run specific test
python -m pytest tests/test_web_search_repository.py
```

### Database Operations
```bash
# The application uses PostgreSQL with async SQLAlchemy
# Connection configured via environment variables in myapi/.env
# Schema: crypto (as defined in models)
```

### Key Configuration
- Environment variables loaded from `myapi/.env`
- Database connection pooling with retry logic
- CORS configured for development and production origins
- Logging configured for AWS Lambda compatibility

## Backend Performance

- MUST: Use async/await for I/O operations
- MUST: Implement database query optimization
- SHOULD: Use caching for expensive operations
- SHOULD: Implement pagination for large datasets
- SHOULD: Monitor API response times

## Python/FastAPI Rules - General Principles

- MUST: Follow PEP 8 style guide
- MUST: Use type hints for all function parameters and return values
- MUST: Use async/await for I/O operations
- SHOULD: Use descriptive variable and function names
- SHOULD: Keep functions small and focused

## FastAPI Specific

- MUST: Use Pydantic models for request/response validation
- MUST: Use dependency injection for database sessions and auth
- MUST: Define proper HTTP status codes for responses
- MUST: Use proper exception handling with HTTPException
- SHOULD: Group related endpoints in separate router files
- SHOULD: Use response_model for endpoint documentation

## Database & Models

- MUST: Use SQLAlchemy async for database operations
- MUST: Define separate Pydantic schemas for create/update/read operations
- MUST: Use proper database migrations with Alembic
- SHOULD: Use database transactions for data consistency
- SHOULD: Implement proper database indexing