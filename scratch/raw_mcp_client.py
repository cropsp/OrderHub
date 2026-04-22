import httpx
import json
import time

def test_raw_mcp():
    base_url = "http://127.0.0.1:3001"
    
    print(f"Connecting to {base_url}/sse...")
    with httpx.stream("GET", f"{base_url}/sse", headers={"Accept": "text/event-stream"}, timeout=30) as response:
        endpoint = None
        for line in response.iter_lines():
            if line.startswith("event: endpoint"):
                # Next line should be data: ...
                continue
            if line.startswith("data:"):
                endpoint = line.replace("data: ", "").strip()
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
                    "instruction": "Open http://localhost:3000 and tell me the Net Profit value"
                }
            }
        }
        
        print("Calling run_browser_agent...")
        r = httpx.post(full_endpoint_url, json=call_payload, timeout=60)
        print(f"Call status: {r.status_code}")
        
        # Now wait for the result in the SSE stream
        print("Waiting for response in SSE stream...")
        for line in response.iter_lines():
            if line.startswith("data:"):
                data = json.loads(line.replace("data: ", "").strip())
                if data.get("id") == 2:
                    print("\n=== CRM VISUAL TEST RESULT ===")
                    print(json.dumps(data.get("result"), indent=2))
                    print("==============================\n")
                    break

if __name__ == "__main__":
    test_raw_mcp()
