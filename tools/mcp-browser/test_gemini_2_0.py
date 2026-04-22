import httpx
import json
import time
import sys

def test_gemini_2_0_mcp():
    base_url = "http://127.0.0.1:3001"
    
    print(f"Connecting to Gemini 2.0 Flash MCP server at {base_url}/sse...")
    try:
        with httpx.stream("GET", f"{base_url}/sse", headers={"Accept": "text/event-stream"}, timeout=60) as response:
            endpoint = None
            buffer = ""
            
            print("Waiting for session endpoint...")
            for chunk in response.iter_text():
                buffer += chunk
                if "data:" in buffer and "\n\n" in buffer:
                    for line in buffer.split("\n"):
                        if line.startswith("data:"):
                            endpoint = line.replace("data:", "").strip()
                            break
                    if endpoint:
                        break
            
            if not endpoint:
                print("Failed to get endpoint from SSE. Server might still be starting.")
                return
                
            full_endpoint_url = f"{base_url}{endpoint}" if endpoint.startswith("/") else endpoint
            print(f"Found session endpoint: {full_endpoint_url}")
            
            # Step 2: Initialize
            init_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "gemini-2-test-client", "version": "2.0.0"}
                }
            }
            
            print("Initializing session...")
            r = httpx.post(full_endpoint_url, json=init_payload, timeout=10)
            
            # Step 3: Call tool
            call_payload = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "run_browser_agent",
                    "arguments": {
                        "instruction": "Navigate to http://localhost:3000. Take a screenshot (describe it) and tell me the value of 'Net Profit'. Verify that the page is alive. Finish the task."
                    }
                }
            }
            
            print("🚀 Sending task to Gemini 2.0 Flash...")
            r = httpx.post(full_endpoint_url, json=call_payload, timeout=180)
            
            print("Waiting for response stream...")
            buffer = ""
            for chunk in response.iter_text():
                buffer += chunk
                # Print raw events for debugging
                if "data:" in buffer:
                    try:
                        start = buffer.find("data: ") + 6
                        end = buffer.find("\n", start)
                        if end != -1:
                            data_str = buffer[start:end].strip()
                            data = json.loads(data_str)
                            if data.get("id") == 2:
                                print("\n✨ GEMINI 2.0 FLASH REPORT:")
                                result = data.get("result", {})
                                for content in result.get("content", []):
                                    if content.get("type") == "text":
                                        print(content.get("text"))
                                return
                            buffer = buffer[end:]
                    except:
                        pass
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    test_gemini_2_0_mcp()
