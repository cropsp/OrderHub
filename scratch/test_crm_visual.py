import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_test")

async def test_crm_visual():
    server_url = "http://127.0.0.1:3001/sse"
    crm_url = "http://localhost:3000"
    
    instruction = f"Open {crm_url}. Wait for the dashboard to load. Describe the 'Net Profit' and 'Active Orders' you see on the screen. Tell me the name of the logged in user."
    
    logger.info(f"Connecting to MCP server at {server_url}...")
    
    try:
        async with sse_client(server_url) as (read, write):
            async with ClientSession(read, write) as session:
                logger.info("Initializing session...")
                await session.initialize()
                
                logger.info(f"Running browser agent with instruction: {instruction}")
                # We assume the tool name is 'run_browser_agent' and it takes an 'instruction' argument
                result = await session.call_tool("run_browser_agent", {"instruction": instruction})
                
                print("\n=== CRM VISUAL TEST REPORT ===")
                for content in result:
                    if content.type == "text":
                        print(content.text)
                print("==============================\n")
                
    except Exception as e:
        logger.error(f"Failed to run CRM test: {e}")

if __name__ == "__main__":
    asyncio.run(test_crm_visual())
