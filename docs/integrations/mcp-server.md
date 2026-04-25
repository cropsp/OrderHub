# MCP Server — Vision & Status

## Purpose

OrderHub's MCP server enables external AI agents (Claude Desktop, OpenClaw, Hermes, or any MCP-compatible client) to operate as a virtual manager inside the CRM. The goal is full operational parity with a human manager:

- Create and print shipping labels (Nova Poshta TTN)
- Monitor order pipeline and status changes
- Manage product catalog and stock levels
- Track inventory and alert when products are running low
- Execute any action a human manager can perform in the UI

## Current State (as of this audit)

- MCP server is implemented with SSE transport (`GET /api/mcp/sse`, `POST /api/mcp/messages`)
- JWT auth guards are in place (SEC-1, completed in Sprint 6)
- Basic tool exposure is functional
- The server is NOT the current development priority

## What Works

- SSE connection with JWT authentication
- Basic message exchange between agent and server
- Auth protection on both `/sse` and `/messages` endpoints

## Known Issues (Deferred)

- **SEC-06**: No session-keyed transports — concurrent SSE connections may experience cross-talk. Must be fixed before multi-user MCP usage.
- `handle_post_message` has a mypy signature mismatch
- No rate limiting on MCP endpoints (SEC-15, in TECH_DEBT)

## Development Plan

MCP server development is paused until the core CRM is stable:

1. First: complete production deployment (Sprint 11)
2. First: resolve all HIGH/CRITICAL items from security audit
3. Then: resume MCP development with session isolation (SEC-06)
4. Then: expand tool surface (order creation, TTN printing, inventory queries)
5. Then: add rate limiting and audit logging for agent actions

## Architecture Notes

- MCP router: `backend/routers/mcp.py`
- Transport: SSE (Server-Sent Events)
- Auth: JWT token in `Authorization` header
- Protocol: Model Context Protocol specification

## How to Test (when development resumes)

1. Start the backend
2. Connect via MCP client (e.g. Claude Desktop) with a valid JWT
3. Send a test message to verify round-trip
4. Check `backend/logs/server.log` for MCP-related entries
