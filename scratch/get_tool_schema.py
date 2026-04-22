import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client
import json

async def get_tool_schema():
    server_url = "http://127.0.0.1:3001/sse"
    async with sse_client(server_url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            for tool in tools.tools:
                if tool.name == "run_browser_agent":
                    print(json.dumps(tool.inputSchema, indent=2))

if __name__ == "__main__":
    asyncio.run(get_tool_schema())
