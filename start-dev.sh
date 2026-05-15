#!/bin/bash
# OrderHub — Development Server
# Usage: ./start-dev.sh
# Press Ctrl+C to stop all services

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()   { echo -e "${GREEN}[OrderHub]${NC} $1"; }
warn()  { echo -e "${YELLOW}[OrderHub]${NC} $1"; }
error() { echo -e "${RED}[OrderHub]${NC} $1"; }

PIDS=()

cleanup() {
    echo ""
    warn "Shutting down..."

    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null
        fi
    done

    log "Stopping Postgres..."
    cd "$PROJECT_DIR" && docker compose -f docker-compose.dev.yml stop postgres 2>/dev/null

    log "All services stopped. Bye!"
    exit 0
}

trap cleanup SIGINT SIGTERM

# ── 1. Postgres ────────────────────────────────────────────
log "Starting Postgres..."
cd "$PROJECT_DIR"
docker compose -f docker-compose.dev.yml up -d postgres

log "Waiting for Postgres to be ready..."
until docker compose -f docker-compose.dev.yml exec -T postgres pg_isready -U crm -q 2>/dev/null; do
    sleep 1
done
log "Postgres is ready ✓"

# ── 2. Backend ─────────────────────────────────────────────
log "Starting backend (port 8000)..."
cd "$BACKEND_DIR"

if [ ! -d "venv" ]; then
    warn "venv not found, creating..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt -q
else
    source venv/bin/activate
fi

# Seed DB if empty
python seed.py --if-empty 2>/dev/null && log "DB seeded ✓" || true

uvicorn main:app --reload --host 0.0.0.0 --port 8000 &
PIDS+=($!)
log "Backend PID: ${PIDS[-1]} ✓"

# ── 3. Frontend ────────────────────────────────────────────
log "Starting frontend (port 3000)..."
cd "$FRONTEND_DIR"

if [ ! -d "node_modules" ]; then
    warn "node_modules not found, running npm install..."
    npm install -q
fi

npm run dev &
PIDS+=($!)
log "Frontend PID: ${PIDS[-1]} ✓"

# ── Ready ──────────────────────────────────────────────────
echo ""
echo -e "${GREEN}┌─────────────────────────────────────────┐${NC}"
echo -e "${GREEN}│  OrderHub is running                    │${NC}"
echo -e "${GREEN}│  Frontend:  http://localhost:3000       │${NC}"
echo -e "${GREEN}│  Backend:   http://localhost:8000       │${NC}"
echo -e "${GREEN}│  API Docs:  http://localhost:8000/docs  │${NC}"
echo -e "${GREEN}│                                         │${NC}"
echo -e "${GREEN}│  Press Ctrl+C to stop all services      │${NC}"
echo -e "${GREEN}└─────────────────────────────────────────┘${NC}"
echo ""

# Wait until Ctrl+C
wait
