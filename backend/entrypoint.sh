#!/bin/bash
set -e

echo "=== OrderHub Backend Starting ==="

# Install idlaser as an editable package from the bind-mounted /idlaser path.
# Idempotent: pip detects the existing install and short-circuits on subsequent
# starts. Skipped (with a warning) if /idlaser is missing — designer flow still
# works without it.
if [ -d "/idlaser" ]; then
    echo "Installing idlaser (editable) from /idlaser..."
    pip install --no-cache-dir -e /idlaser
else
    echo "WARNING: /idlaser bind-mount not present — Generate Draft will be unavailable."
fi

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
