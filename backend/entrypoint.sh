#!/bin/bash
set -e

echo "=== OrderHub Backend Starting ==="

# Run Alembic migrations
echo "Running database migrations..."
alembic upgrade head

# Check if --dev flag is passed and seed data if DB is empty
if [ "$1" = "--dev" ]; then
    echo "Development mode: checking seed data..."
    python seed.py --if-empty
fi

# Start the application
echo "Starting uvicorn server..."
exec uvicorn main:app --host 0.0.0.0 --port 8000 --reload
