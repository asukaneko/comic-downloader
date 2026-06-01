"""NekoBot MCP Server

Main entry point for the MCP server.
Creates a FastMCP instance, registers all tools/resources/prompts,
and starts the server.

Usage:
    python -m nbot.mcp.server
"""

import asyncio
import json
import logging
import sys
from typing import Any

from nbot.mcp.context import MCPContext, create_mcp_context
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

    mcp = FastMCP(
        "nekobot-gateway",
        instructions="NekoBot Gateway control and observation interface for AI Agents",
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

    # Default config for local stdio mode
    config = {
        "transport": "stdio",
        "permissions": {
            "default_scopes": [
                "gateway.read",
                "events.query",
                "queue.read",
                "node.read",
            ],
        },
        "tools": {
            "gateway_send_message": {
                "enabled": False,
                "require_confirmation": True,
            },
            "gateway_receive_message": {
                "enabled": True,
                "require_confirmation": False,
            },
            "gateway_retry_dead_letter": {
                "enabled": True,
                "require_confirmation": True,
            },
        },
        "audit": {
            "enabled": True,
            "log_args": True,
            "redact_fields": ["token", "secret", "password", "authorization"],
        },
    }

    mcp = create_mcp_server(config)
    _log.info("[MCP] Starting NekoBot Gateway MCP Server (stdio)...")

    # Run with stdio transport
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
