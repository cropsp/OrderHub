"""OrderHub MCP server — configuration.

Settings come from the environment. MCP clients pass an `env` block in their
server config, so environment variables are the primary mechanism; a local
`mcp_server/.env` is loaded first so the server can be hand-run during
development without exporting anything.

The agent password is a real login credential (MCP-WAREHOUSE §5.7 chose
password + refresh-cookie over an `api_keys` table for the local stdio v1).
Keep it in the OS keychain or in `mcp_server/.env`, which is git-ignored.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

DEFAULT_API_URL = "http://localhost:8000"
DEFAULT_AGENT_EMAIL = "agent@orderhub.dev"


class ConfigError(RuntimeError):
    """Raised at startup when required configuration is missing.

    Fails loudly on purpose: a half-configured server would surface as a
    confusing 401 on the agent's first tool call instead of at launch.
    """


@dataclass(frozen=True)
class Config:
    api_url: str
    agent_email: str
    agent_password: str
    timeout_s: float

    @classmethod
    def from_env(cls) -> "Config":
        password = os.environ.get("ORDERHUB_AGENT_PASSWORD", "").strip()
        if not password:
            raise ConfigError(
                "ORDERHUB_AGENT_PASSWORD is not set. Put it in mcp_server/.env "
                "or in the `env` block of your MCP client's server config. "
                "See mcp_server/README.md."
            )
        return cls(
            api_url=os.environ.get("ORDERHUB_API_URL", DEFAULT_API_URL).rstrip("/"),
            agent_email=os.environ.get("ORDERHUB_AGENT_EMAIL", DEFAULT_AGENT_EMAIL),
            agent_password=password,
            timeout_s=float(os.environ.get("ORDERHUB_TIMEOUT_S", "30")),
        )
