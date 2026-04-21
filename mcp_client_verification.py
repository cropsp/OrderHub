import asyncio
import json
import anyio
from mcp import ClientSession
from mcp.client.sse import sse_client

async def run_verification():
    url = "http://127.0.0.1:3001/sse"
    print(f"Connecting to MCP server (browser-use) at {url}...")
    
    try:
        async with sse_client(url) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                print("Initializing session...")
                await session.initialize()
                
                task_prompt = (
                    "Go to http://localhost:3000. "
                    "Login with email 'owner@orderhub.dev' and password 'owner123'. "
                    "Verify you see dashboard stats and say 'Login Successful'."
                )
                
                print(f"Sending task to browser agent: {task_prompt}")
                
                # Using a longer timeout if possible (mcp-sdk depends on anyio)
                result = await session.call_tool("run_browser_agent", {"task": task_prompt})
                
                print("\n=== Raw Result Debug ===")
                # Print the whole object to see what we are getting
                print(result)
                
                print("\n=== Agent Result Content ===")
                found_text = False
                for content in result.content:
                    print(f"Content Type: {type(content)}")
                    if hasattr(content, 'text'):
                        print(f"Text: {content.text}")
                        found_text = True
                    else:
                        print(f"Other content fields: {dir(content)}")
                
                if not found_text:
                    print("No text content found in result.")
                print("========================\n")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    anyio.run(run_verification)
