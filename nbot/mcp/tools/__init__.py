"""MCP Tools 模块"""

from nbot.mcp.tools.gateway_tools import register_gateway_tools
from nbot.mcp.tools.web_tools import register_web_tools

__all__ = ["register_gateway_tools", "register_web_tools"]
