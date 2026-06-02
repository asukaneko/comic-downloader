"""NekoBot MCP Server

Main entry point for the MCP server.
Creates a FastMCP instance, registers all tools/resources/prompts,
and starts the server.

Usage:
    python -m nbot.mcp.server
"""

import logging
import sys
from typing import Any

from nbot.mcp.config import load_mcp_config
from nbot.mcp.context import create_mcp_context
from nbot.mcp.prompts.diagnose_prompt import register_diagnose_prompts
from nbot.mcp.resources.gateway_resources import register_gateway_resources
from nbot.mcp.tools.gateway_tools import register_gateway_tools

_log = logging.getLogger(__name__)


def create_mcp_server(config: dict[str, Any] | None = None) -> Any:
    """Create and configure the NekoBot MCP Server

    Args:
        config: MCP configuration dict

    Returns:
        Configured FastMCP instance
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        _log.error("[MCP] mcp package not installed. Run: pip install mcp")
        sys.exit(1)

    config = config or {}
    ctx = create_mcp_context(config)

    server_cfg = config.get("server", {})
    host = server_cfg.get("host", "127.0.0.1")
    port = server_cfg.get("port", 5001)

    mcp = FastMCP(
        "nekobot-gateway",
        instructions="NekoBot Gateway control and observation interface for AI Agents",
        host=host,
        port=port,
    )

    # Register tools
    register_gateway_tools(mcp, ctx)
    _log.info("[MCP] Tools registered")

    # Register resources
    register_gateway_resources(mcp, ctx)
    _log.info("[MCP] Resources registered")

    # Register prompts
    register_diagnose_prompts(mcp, ctx)
    _log.info("[MCP] Prompts registered")

    return mcp


def main():
    """Main entry point for CLI usage"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    config = load_mcp_config()
    transport = config.get("transport", "stdio")

    mcp = create_mcp_server(config)

    if transport == "streamable-http":
        host = config.get("server", {}).get("host", "127.0.0.1")
        port = config.get("server", {}).get("port", 5001)
        _log.info("[MCP] Starting NekoBot Gateway MCP Server (streamable-http) on %s:%s ...", host, port)
    else:
        _log.info("[MCP] Starting NekoBot Gateway MCP Server (stdio)...")

    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
