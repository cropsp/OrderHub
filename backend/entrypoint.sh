#!/bin/bash
set -e

echo "=== OrderHub Backend Starting ==="

# OQ-H — warn if .env still references the pre-S005 bind-mount paths.
# Generate Draft will fail with a "file not found" lifespan warning unless
# the operator either unsets these vars (to pick up new defaults) or
# updates them to /app/external/idlaser/... paths. Non-fatal: the rest
# of the app keeps working (CLAUDE.md "Idlaser missing is non-fatal").
if [[ "${IDLASER_TEMPLATE_PATH:-}" == /idlaser/* ]] || [[ "${IDLASER_MODEL_PATH:-}" == /idlaser/* ]]; then
    echo "WARNING: .env still references pre-S005 IDLASER_* paths under /idlaser/."
    echo "  Current IDLASER_TEMPLATE_PATH=${IDLASER_TEMPLATE_PATH:-<unset>}"
    echo "  Current IDLASER_MODEL_PATH=${IDLASER_MODEL_PATH:-<unset>}"
    echo "  New defaults (set via backend/config.py): /app/external/idlaser/7001.svg"
    echo "                                            /app/external/idlaser/models/card_detector.onnx"
    echo "  Update .env or unset these vars. Generate Draft will fail until corrected."
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
