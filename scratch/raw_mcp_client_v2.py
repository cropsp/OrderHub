import httpx
import json
import sys

def test_raw_mcp():
    base_url = "http://127.0.0.1:3001"
    
    print(f"Connecting to {base_url}/sse...")
    try:
        with httpx.stream("GET", f"{base_url}/sse", headers={"Accept": "text/event-stream"}, timeout=30) as response:
            endpoint = None
            buffer = ""
            
            # Read first part to get endpoint
            for chunk in response.iter_text():
                buffer += chunk
                if "data:" in buffer and "\n\n" in buffer:
                    # Very simple parse
                    for line in buffer.split("\n"):
                        if line.startswith("data:"):
                            endpoint = line.replace("data:", "").strip()
                            break
                    if endpoint:
                        break
            
            if not endpoint:
                print("Failed to get endpoint from SSE")
                return
                
            full_endpoint_url = f"{base_url}{endpoint}" if endpoint.startswith("/") else endpoint
            print(f"Found endpoint: {full_endpoint_url}")
            
            # Step 2: Initialize
            init_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "raw-test-client", "version": "1.0.0"}
                }
            }
            
            print("Sending initialize...")
            r = httpx.post(full_endpoint_url, json=init_payload, timeout=10)
            print(f"Init status: {r.status_code}")
            
            # Step 3: Call tool
            call_payload = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "run_browser_agent",
                    "arguments": {
                        "instruction": "Open http://localhost:3000 and report the Net Profit value. Finish the task."
                    }
                }
            }
            
            print("Calling run_browser_agent...")
            r = httpx.post(full_endpoint_url, json=call_payload, timeout=120)
            print(f"Call status: {r.status_code}")
            
            # Wait for result
            print("Waiting for response...")
            buffer = ""
            for chunk in response.iter_text():
                buffer += chunk
                if "data:" in buffer:
                    # Try to find a complete JSON
                    try:
                        start = buffer.find("data: ") + 6
                        end = buffer.find("\n", start)
                        if end != -1:
                            data_str = buffer[start:end].strip()
                            data = json.loads(data_str)
                            if data.get("id") == 2:
                                print("\n=== RESULT ===")
                                print(json.dumps(data.get("result"), indent=2))
                                return
                            # Clear buffer up to end
                            buffer = buffer[end:]
                    except:
                        pass
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    test_raw_mcp()
