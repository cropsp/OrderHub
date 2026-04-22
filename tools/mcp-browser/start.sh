#!/bin/bash
# Dedicated MCP Browser Server Startup Script
# This tool is used for verification and testing of the OrderHub CRM.

echo "🌐 Starting Gemini 2.0 Flash Browser Agent on port 3001..."

# API Key
export GOOGLE_API_KEY="your key"

# Browser Settings
export BROWSER_USE_VISION="true"
export MCP_BROWSER_HEADLESS="true" # Setting to true for cleaner background execution

# Run using uvx with proxy for SSE support
uvx mcp-proxy --port 3001 \
  -- /usr/bin/env \
  MCP_LLM_PROVIDER=google \
  MCP_LLM_MODEL_NAME=gemini-2.0-flash \
  MCP_LLM_API_KEY=$GOOGLE_API_KEY \
  BROWSER_USE_VISION=true \
  BROWSER_VISION_ENABLED=true \
  MCP_BROWSER_HEADLESS=true \
  MCP_SERVER_LOGGING_LEVEL=DEBUG \
  uvx mcp-server-browser-use
