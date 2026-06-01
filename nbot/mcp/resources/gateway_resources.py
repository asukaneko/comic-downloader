"""MCP Gateway Resources

Register read-only Resources exposing Gateway status, stats, capabilities.

URI design:
  nekobot://gateway/status
  nekobot://gateway/stats
  nekobot://gateway/capabilities
  nekobot://gateway/queue/stats
  nekobot://gateway/nodes
"""

import json
import logging
from typing import Any

from nbot.mcp.context import MCPContext

_log = logging.getLogger(__name__)


def register_gateway_resources(mcp_server: Any, ctx: MCPContext) -> None:
    """Register all Gateway MCP Resources"""
    facade = ctx.facade

    @mcp_server.resource("nekobot://gateway/status")
    async def gateway_status_resource() -> str:
        """Gateway current running status"""
        try:
            result = await facade.get_status()
            return json.dumps(result, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)

    @mcp_server.resource("nekobot://gateway/stats")
    async def gateway_stats_resource() -> str:
        """Gateway event, delivery, dedupe, queue stats"""
        try:
            result = await facade.get_stats()
            return json.dumps(result, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)

    @mcp_server.resource("nekobot://gateway/capabilities")
    async def gateway_capabilities_resource() -> str:
        """Current MCP capability manifest"""
        try:
            result = await facade.get_capabilities()
            return json.dumps(result, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)

    @mcp_server.resource("nekobot://gateway/queue/stats")
    async def gateway_queue_stats_resource() -> str:
        """Async queue status"""
        try:
            result = await facade.get_queue_stats()
            return json.dumps(result, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)

    @mcp_server.resource("nekobot://gateway/nodes")
    async def gateway_nodes_resource() -> str:
        """All registered nodes"""
        try:
            result = await facade.list_nodes()
            return json.dumps(result, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
