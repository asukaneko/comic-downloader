"""MCP Prompts

Register diagnostic and testing prompt templates.

Prompts:
  diagnose_gateway_failure - Diagnose Gateway failure by trace_id
  test_channel_message - Test channel message flow
  inspect_node_health - Inspect node health
"""

import logging
from typing import Any

from nbot.mcp.context import MCPContext

_log = logging.getLogger(__name__)


def register_diagnose_prompts(mcp_server: Any, ctx: MCPContext) -> None:
    """Register all Gateway MCP Prompts"""

    @mcp_server.prompt()
    def diagnose_gateway_failure(trace_id: str = "") -> str:
        """Diagnose Gateway failure messages"""
        return (
            "Please query the Gateway event chain, delivery records, and queue status "

            f"for trace_id={trace_id}. "

            "Determine which stage the failure occurred in: "

            "authentication, rate limiting, parsing, dedup, dispatch, delivery, or queue. "

            "Finally, provide the root cause, impact scope, and fix suggestions."
        )

    @mcp_server.prompt()
    def test_channel_message(channel_id: str = "", message: str = "") -> str:
        """Test a channel message processing flow"""
        return (
            f"Please simulate sending a test message to channel={channel_id} "

            f"with content={message}. "

            "Then query the trace chain to determine if the channel adapter, "

            "AI Core dispatch, and reply delivery are working correctly."
        )

    @mcp_server.prompt()
    def inspect_node_health(node_id: str = "") -> str:
        """Inspect node health status"""
        return (
            f"Please query the registration info, recent heartbeat, load, "

            f"status changes, and related events for node={node_id}. "

            "Determine if the node is healthy."
        )
