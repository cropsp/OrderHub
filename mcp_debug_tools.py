import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client
import anyio
import json

async def list_tools():
    url = "http://127.0.0.1:3001/sse"
    async with sse_client(url) as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()
            result = await session.list_tools()
            for tool in result.tools:
                print(f"Tool: {tool.name}")
                print(f"Schema: {json.dumps(tool.inputSchema, indent=2)}")

if __name__ == "__main__":
    anyio.run(list_tools)
