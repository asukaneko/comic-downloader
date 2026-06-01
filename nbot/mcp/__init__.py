"""NekoBot MCP Server

通过 MCP (Model Context Protocol) 暴露 Gateway 核心能力，
使 Claude Code、Cursor、ChatGPT Agent 等外部智能体可以
安全、标准地调用 NekoBot 的消息、事件、任务、投递和观测能力。

使用方式：
    python -m nbot.mcp.server
"""

__all__ = ["create_mcp_server"]
