"""OrderHub MCP server — stdio entry point.

Run by an MCP client (Claude Desktop / Claude Code / Cowork), which spawns this
process and speaks JSON-RPC over stdin/stdout. See mcp_server/README.md for the
client configuration block.

    mcp_server/venv/bin/python mcp_server/main.py

Nothing may be written to stdout except MCP protocol frames — stdout *is* the
transport. Diagnostics go to stderr.
"""

import sys

from config import Config, ConfigError
from server import build_server


def main() -> int:
    try:
        config = Config.from_env()
    except ConfigError as exc:
        print(f"orderhub-mcp: {exc}", file=sys.stderr)
        return 2

    mcp, _client = build_server(config)
    print(
        f"orderhub-mcp: serving {config.agent_email} against {config.api_url}",
        file=sys.stderr,
    )
    # Blocks until the client closes stdin. FastMCP owns the event loop, so the
    # client's httpx session is torn down with the process.
    mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
