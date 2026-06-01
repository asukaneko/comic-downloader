"""MCP 上下文管理

管理 MCP Server 运行时所需的 Gateway、Facade、权限等依赖。
负责初始化和注入，MCP Tool/Resource 通过上下文获取所需组件。
"""

import asyncio
import logging
import os
from typing import Any

from nbot.gateway.facade import GatewayFacade
from nbot.gateway.gateway import ChannelGateway, get_gateway, set_gateway
from nbot.gateway.nodes.registry import NodeRegistry

_log = logging.getLogger(__name__)


class MCPContext:
    """MCP 运行时上下文

    持有 Gateway、Facade、NodeRegistry 等共享实例。
    """

    def __init__(
        self,
        gateway: ChannelGateway,
        node_registry: NodeRegistry | None = None,
    ):
        self._gateway = gateway
        self._node_registry = node_registry or NodeRegistry()
        self._facade = GatewayFacade(gateway, self._node_registry)
        self._permissions: dict[str, list[str]] = {}
        self._config: dict[str, Any] = {}

    @property
    def gateway(self) -> ChannelGateway:
        return self._gateway

    @property
    def facade(self) -> GatewayFacade:
        return self._facade

    @property
    def node_registry(self) -> NodeRegistry:
        return self._node_registry

    @property
    def config(self) -> dict[str, Any]:
        return self._config

    def set_config(self, config: dict[str, Any]) -> None:
        """设置 MCP 配置"""
        self._config = config

    def check_permission(self, scope: str) -> bool:
        """检查当前上下文是否具有指定权限

        第一版本地模式默认允许所有只读权限。
        """
        default_scopes = self._config.get("permissions", {}).get("default_scopes", [])
        if scope in default_scopes:
            return True
        # 本地 stdio 模式默认全允许
        if self._config.get("transport", "stdio") == "stdio":
            return True
        return False

    def is_tool_enabled(self, tool_name: str) -> bool:
        """检查工具是否启用"""
        tools_config = self._config.get("tools", {})
        tool_cfg = tools_config.get(tool_name, {})
        return tool_cfg.get("enabled", True)

    def requires_confirmation(self, tool_name: str) -> bool:
        """检查工具是否需要确认"""
        tools_config = self._config.get("tools", {})
        tool_cfg = tools_config.get(tool_name, {})
        return tool_cfg.get("require_confirmation", False)


def create_mcp_context(
    config: dict[str, Any] | None = None,
) -> MCPContext:
    """创建 MCP 上下文

    尝试获取已有的全局 Gateway 实例，
    如果不存在则从配置创建一个。

    Args:
        config: MCP 配置字典

    Returns:
        初始化完成的 MCPContext
    """
    config = config or {}
    gateway = get_gateway()

    if gateway is None:
        _log.info("[MCP] 未找到全局 Gateway，从配置创建")
        from nbot.gateway.gateway import create_gateway_from_config

        gateway = create_gateway_from_config(config)
        set_gateway(gateway)

    node_registry = NodeRegistry()

    ctx = MCPContext(gateway, node_registry)
    ctx.set_config(config)

    _log.info(
        "[MCP] 上下文已创建 mode=%s storage=%s",
        "async" if gateway.async_mode else "sync",
        "sqlite" if gateway.storage else "memory",
    )

    return ctx
