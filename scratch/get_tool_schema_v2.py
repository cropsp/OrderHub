import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client
import json
import logging

logging.basicConfig(level=logging.INFO)

async def get_tool_schema():
    server_url = "http://127.0.0.1:3001/sse"
    try:
        async with sse_client(server_url) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=10)
                tools = await session.list_tools()
                for tool in tools.tools:
                    print(f"TOOL: {tool.name}")
                    print(f"SCHEMA: {json.dumps(tool.inputSchema, indent=2)}")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(get_tool_schema())
