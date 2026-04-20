"""
OrderHub CRM — Main Application

FastAPI application with CORS, exception handlers, and lifespan events.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import get_settings
from routers import (
    auth, users, shops, customers, orders, imports, attachments, dashboard, mcp, shipping
)

from scheduler import start_scheduler

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    print("=== OrderHub CRM starting ===")
    start_scheduler()
    yield
    print("=== OrderHub CRM shutting down ===")


app = FastAPI(
    title="OrderHub CRM",
    description="Order Management CRM for multi-channel e-commerce",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)

# ─── CORS ──────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Exception Handlers ───────────────────────────────────
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": "Resource not found"},
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


# ─── Routers ──────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(shops.router)
app.include_router(customers.router)
app.include_router(orders.router)
app.include_router(imports.router)
app.include_router(attachments.router)
app.include_router(dashboard.router)
app.include_router(mcp.router)
app.include_router(shipping.router)


# ─── Health Check ──────────────────────────────────────────
@app.get("/api/health", tags=["health"])
async def health_check():
    return {"status": "ok", "service": "OrderHub CRM"}
