"""MCP Bridge

管理多个 MCP Server 连接，将 MCP 工具桥接为 AI 可用的 OpenAI function calling 格式。

工具命名规则：mcp__<server_id_short>__<tool_name>
  - server_id_short: UUID 前 8 位
  - tool_name: MCP 原始工具名

用法：
    bridge = get_mcp_bridge()
    bridge.run_async(bridge.connect_server("uuid-xxx", {"transport": "streamable-http", "url": "..."}))
    tools = bridge.get_openai_tool_definitions("uuid-xxx")
    result = bridge.run_async(bridge.execute("uuid-xxx", "tool_name", {"arg": "val"}))
"""

import asyncio
import logging
import threading
from concurrent.futures import Future
from typing import Any

from nbot.mcp.client import MCPRemoteClient

_log = logging.getLogger(__name__)

# 工具名前缀分隔符
_SEP = "__"
_PREFIX = "mcp"


def _make_tool_name(server_id: str, tool_name: str) -> str:
    """生成 MCP 工具的全局唯一名称"""
    short = server_id.replace("-", "")[:8]
    return f"{_PREFIX}{_SEP}{short}{_SEP}{tool_name}"


def _parse_tool_name(full_name: str) -> tuple[str, str] | None:
    """解析 MCP 工具名，返回 (server_id_short, tool_name) 或 None"""
    if not full_name.startswith(_PREFIX + _SEP):
        return None
    parts = full_name.split(_SEP, 2)
    if len(parts) < 3:
        return None
    return parts[1], parts[2]


def mcp_tool_to_openai(tool: dict, server_id: str) -> dict:
    """将 MCP 工具定义转为 OpenAI function calling 格式

    MCP 格式: {"name": "...", "description": "...", "input_schema": {...}}
    OpenAI 格式: {"type": "function", "function": {"name": "...", "description": "...", "parameters": {...}}}
    """
    name = _make_tool_name(server_id, tool["name"])
    parameters = tool.get("input_schema", {})
    if not isinstance(parameters, dict):
        parameters = {"type": "object", "properties": {}}
    # 确保有 type 字段
    if "type" not in parameters:
        parameters["type"] = "object"
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": tool.get("description", ""),
            "parameters": parameters,
        },
    }


class MCPBridge:
    """MCP 连接管理器和工具桥接器"""

    def __init__(self):
        # server_id -> MCPRemoteClient
        self._clients: dict[str, MCPRemoteClient] = {}
        # server_id -> list[mcp_tool_dict]
        self._tool_cache: dict[str, list[dict]] = {}
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: threading.Thread | None = None
        self._loop_ready = threading.Event()

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        """确保持久化事件循环已启动"""
        if self._loop is not None and self._loop.is_running():
            return self._loop

        def _run():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop_ready.set()
            self._loop.run_forever()

        self._loop_thread = threading.Thread(target=_run, name="mcp-bridge-loop", daemon=True)
        self._loop_thread.start()
        self._loop_ready.wait(timeout=10)
        return self._loop

    def run_async(self, coro, timeout: float = 60):
        """在持久化事件循环中运行异步协程，同步等待结果"""
        loop = self._ensure_loop()
        future: Future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)

    async def connect_server(self, server_id: str, config: dict) -> dict:
        """连接到 MCP Server 并缓存工具列表

        Args:
            server_id: 服务器 ID
            config: 连接配置，支持两种格式：
                HTTP: {"transport": "streamable-http", "url": "http://..."}
                Stdio: {"transport": "stdio", "command": "python", "args": ["..."], "env": {...}}

        Returns:
            {"ok": True, "tool_count": N} 或 {"ok": False, "error": "..."}
        """
        # 先断开已有的
        await self.disconnect_server(server_id)

        transport = config.get("transport", "streamable-http")
        if transport == "stdio":
            client = MCPRemoteClient(
                transport="stdio",
                command=config.get("command", ""),
                args=config.get("args", []),
                env=config.get("env"),
            )
        else:
            client = MCPRemoteClient(
                transport="streamable-http",
                url=config.get("url", ""),
            )

        try:
            await client.connect()
            _log.info("[MCP Bridge] connect() 完成，开始 list_tools...")
            tools = await client.list_tools()
            _log.info("[MCP Bridge] list_tools() 返回 %d 个工具", len(tools))
        except BaseException as e:
            _log.error("[MCP Bridge] 连接失败 %s: %s (%s)", config, e, type(e).__name__, exc_info=True)
            try:
                await client.close()
            except BaseException:
                pass
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

        with self._lock:
            self._clients[server_id] = client
            self._tool_cache[server_id] = tools

        _log.info("[MCP Bridge] 已连接 %s (%s), %d 个工具", server_id, transport, len(tools))
        return {"ok": True, "tool_count": len(tools)}

    async def disconnect_server(self, server_id: str) -> None:
        """断开指定服务器"""
        with self._lock:
            client = self._clients.pop(server_id, None)
            self._tool_cache.pop(server_id, None)
        if client:
            try:
                await client.close()
            except Exception:
                pass
            _log.info("[MCP Bridge] 已断开 %s", server_id)

    async def disconnect_all(self) -> None:
        """断开所有服务器"""
        server_ids = list(self._clients.keys())
        for sid in server_ids:
            await self.disconnect_server(sid)

    def is_connected(self, server_id: str) -> bool:
        """检查是否已连接"""
        return server_id in self._clients

    def get_server_tools(self, server_id: str) -> list[dict]:
        """获取指定服务器的 MCP 格式工具列表"""
        return list(self._tool_cache.get(server_id, []))

    def get_openai_tool_definitions(self, server_id: str) -> list[dict]:
        """获取指定服务器的 OpenAI 格式工具定义"""
        tools = self._tool_cache.get(server_id, [])
        return [mcp_tool_to_openai(t, server_id) for t in tools]

    def get_all_openai_tools(self) -> list[dict]:
        """获取所有已连接服务器的 OpenAI 格式工具定义"""
        all_tools = []
        with self._lock:
            for server_id, tools in self._tool_cache.items():
                all_tools.extend(mcp_tool_to_openai(t, server_id) for t in tools)
        return all_tools

    async def execute(self, server_id: str, tool_name: str, arguments: dict) -> Any:
        """执行 MCP 工具调用

        Returns:
            工具返回的结果（dict 或 str）
        """
        with self._lock:
            client = self._clients.get(server_id)
        if not client:
            return {"ok": False, "error": f"MCP server {server_id} not connected"}
        try:
            result = await client.call_tool(tool_name, arguments)
            return result
        except Exception as e:
            _log.error("[MCP Bridge] 工具调用失败 %s/%s: %s", server_id, tool_name, e)
            return {"ok": False, "error": str(e)}

    async def execute_by_full_name(self, full_name: str, arguments: dict) -> Any:
        """通过全局工具名执行

        解析 mcp__<server_short>__<tool_name> 格式，找到对应 server 并调用。
        """
        parsed = _parse_tool_name(full_name)
        if not parsed:
            return {"ok": False, "error": f"Not an MCP tool: {full_name}"}

        server_short, tool_name = parsed

        # 找到匹配的 server_id
        with self._lock:
            server_id = None
            for sid in self._clients:
                if sid.replace("-", "")[:8] == server_short:
                    server_id = sid
                    break
        if not server_id:
            return {"ok": False, "error": f"MCP server not found for {full_name}"}

        return await self.execute(server_id, tool_name, arguments)

    def get_status(self) -> dict:
        """获取所有服务器状态"""
        status = {}
        with self._lock:
            for server_id in list(self._clients.keys()) + list(self._tool_cache.keys()):
                if server_id not in status:
                    status[server_id] = {
                        "connected": server_id in self._clients,
                        "tool_count": len(self._tool_cache.get(server_id, [])),
                    }
        return status


# 全局单例
_bridge: MCPBridge | None = None
_bridge_lock = threading.Lock()


def get_mcp_bridge() -> MCPBridge:
    """获取全局 MCPBridge 单例"""
    global _bridge
    if _bridge is None:
        with _bridge_lock:
            if _bridge is None:
                _bridge = MCPBridge()
    return _bridge
