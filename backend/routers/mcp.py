"""
OrderHub CRM — MCP Server Integration
Exposes CRM tools via Server-Sent Events (SSE) for local AI agents.
"""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from database import get_db, async_session_factory
from models.order import Order, OrderStatus
from models.user import User
from routers.dependencies import get_current_user
import mcp.types as types
from mcp.server import Server
from mcp.server.sse import SseServerTransport


router = APIRouter(prefix="/api/mcp", tags=["mcp"])

# Create MCP Server instance
mcp_server = Server("orderhub-core")

# Global reference to the SSE transport for this instance
# In a robust production setup, this would need to handle multiple clients
# via a session manager, but for a single local agent this is sufficient.
sse_transport: SseServerTransport | None = None


@mcp_server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """Register tools available to the AI agent."""
    return [
        types.Tool(
            name="get_order_stats",
            description="Get high-level dashboard statistics (counts by status)",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        types.Tool(
            name="list_orders",
            description="List recent active orders",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 20}
                },
            },
        )
    ]


@mcp_server.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Execute a tool request from the AI agent."""
    if not arguments:
        arguments = {}

    if name == "get_order_stats":
        async with async_session_factory() as db:
            status_query = select(Order.status, func.count()).group_by(Order.status)
            result = await db.execute(status_query)
            counts = {status.value: count for status, count in result.all()}
            
            return [types.TextContent(
                type="text",
                text=f"Order status breakdown: {counts}"
            )]

    elif name == "list_orders":
        limit = arguments.get("limit", 20)
        async with async_session_factory() as db:
            query = (
                select(Order)
                .where(Order.status != OrderStatus.COMPLETED)
                .order_by(Order.ordered_at.desc())
                .limit(limit)
            )
            result = await db.execute(query)
            orders = result.scalars().all()
            
            lines = [f"Found {len(orders)} active orders:"]
            for o in orders:
                lines.append(f"- #{o.external_id} | Title: {o.title} | Status: {o.status.value} | Total: {o.total_price} {o.currency}")
                
            return [types.TextContent(
                type="text",
                text="\n".join(lines)
            )]
            
    raise Exception(f"Tool not found: {name}")


@router.get("/sse")
async def handle_sse(request: Request, current_user: User = Depends(get_current_user)):
    """
    Endpoint for AI agent to connect to MCP via Server-Sent Events.
    Connect here with the Claude Desktop SSE transport.
    """
    global sse_transport
    
    # Standard MCP flow uses a single URL for POST messages relative to the SSE URL
    transport = SseServerTransport("/api/mcp/messages")
    sse_transport = transport

    async def sse_handler():
        async with transport:
            await mcp_server.run(
                transport,
                mcp_server.create_initialization_options()
            )
            yield ""

    return StreamingResponse(sse_handler(), media_type="text/event-stream")


@router.post("/messages")
async def handle_messages(request: Request, current_user: User = Depends(get_current_user)):
    """Endpoint for AI agent to send JSON-RPC requests to the MCP server."""
    global sse_transport
    
    if not sse_transport:
        raise HTTPException(status_code=400, detail="SSE transport not initialized. Connect to /sse first.")
        
    # Pipe the incoming request JSON into the MCP transport
    await sse_transport.handle_post_message(await request.json())
    return Response(status_code=202)
