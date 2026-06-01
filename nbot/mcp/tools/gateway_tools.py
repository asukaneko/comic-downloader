"""MCP Gateway Tools

注册所有 Gateway 相关的 MCP Tools。
每个 Tool 对应一个 GatewayFacade 方法调用。
"""

import json
import logging
from typing import Any

from nbot.mcp.context import MCPContext
from nbot.mcp.errors import format_mcp_error
from nbot.mcp.permissions import audit_log_entry, check_permission

_log = logging.getLogger(__name__)


def register_gateway_tools(mcp_server: Any, ctx: MCPContext) -> None:
    """注册所有 Gateway MCP Tools"""
    facade = ctx.facade

    # ========================
    # 只读 Tools
    # ========================

    @mcp_server.tool()
    async def gateway_get_status() -> str:
        """查看 Gateway 健康状态"""
        try:
            result = await facade.get_status()
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps(format_mcp_error(e), ensure_ascii=False)

    @mcp_server.tool()
    async def gateway_get_stats() -> str:
        """查看事件、投递、去重、队列统计"""
        try:
            result = await facade.get_stats()
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps(format_mcp_error(e), ensure_ascii=False)

    @mcp_server.tool()
    async def gateway_query_trace(trace_id: str) -> str:
        """根据 trace_id 查询完整事件链路"""
        if not check_permission("gateway_query_trace", _get_scopes(ctx)):
            return json.dumps({"ok": False, "error": {"code": "permission_denied", "message": "no permission"}}, ensure_ascii=False)
        try:
            result = await facade.query_trace(trace_id)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps(format_mcp_error(e, trace_id=trace_id), ensure_ascii=False)

    @mcp_server.tool()
    async def gateway_query_events(
        channel_id: str = "",
        status: str = "",
        event_type: str = "",
        limit: int = 50,
    ) -> str:
        """按条件查询事件历史"""
        if not check_permission("gateway_query_events", _get_scopes(ctx)):
            return json.dumps({"ok": False, "error": {"code": "permission_denied", "message": "no permission"}}, ensure_ascii=False)
        try:
            result = await facade.query_events(
                channel_id=channel_id,
                status=status,
                event_type=event_type,
                limit=limit,
            )
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps(format_mcp_error(e), ensure_ascii=False)

    @mcp_server.tool()
    async def gateway_query_deliveries(
        trace_id: str = "",
        channel_id: str = "",
        status: str = "",
        limit: int = 20,
    ) -> str:
        """查询回复投递记录"""
        if not check_permission("gateway_query_deliveries", _get_scopes(ctx)):
            return json.dumps({"ok": False, "error": {"code": "permission_denied", "message": "no permission"}}, ensure_ascii=False)
        try:
            result = await facade.query_deliveries(
                trace_id=trace_id,
                channel_id=channel_id,
                status=status,
                limit=limit,
            )
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps(format_mcp_error(e), ensure_ascii=False)

    @mcp_server.tool()
    async def gateway_get_queue_stats() -> str:
        """查看异步队列状态"""
        if not check_permission("gateway_get_queue_stats", _get_scopes(ctx)):
            return json.dumps({"ok": False, "error": {"code": "permission_denied", "message": "no permission"}}, ensure_ascii=False)
        try:
            result = await facade.get_queue_stats()
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps(format_mcp_error(e), ensure_ascii=False)

    @mcp_server.tool()
    async def gateway_list_nodes(
        node_type: str = "",
        status: str = "",
    ) -> str:
        """列出所有节点"""
        if not check_permission("gateway_list_nodes", _get_scopes(ctx)):
            return json.dumps({"ok": False, "error": {"code": "permission_denied", "message": "no permission"}}, ensure_ascii=False)
        try:
            result = await facade.list_nodes(node_type=node_type, status=status)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps(format_mcp_error(e), ensure_ascii=False)

    @mcp_server.tool()
    async def gateway_get_node(node_id: str) -> str:
        """获取节点详情"""
        if not check_permission("gateway_get_node", _get_scopes(ctx)):
            return json.dumps({"ok": False, "error": {"code": "permission_denied", "message": "no permission"}}, ensure_ascii=False)
        try:
            result = await facade.get_node(node_id)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps(format_mcp_error(e), ensure_ascii=False)

    # ========================
    # 操作型 Tools
    # ========================

    @mcp_server.tool()
    async def gateway_receive_message(
        channel_id: str,
        raw_event: dict,
        headers: dict | None = None,
        remote_addr: str = "127.0.0.1",
        confirm: bool = False,
    ) -> str:
        """模拟或提交一条频道消息，让 Gateway 按正常管线处理

        Args:
            confirm: 高危操作需显式确认 (confirm=true)
        """
        if not check_permission("gateway_receive_message", _get_scopes(ctx)):
            return json.dumps({"ok": False, "error": {"code": "permission_denied", "message": "no permission"}}, ensure_ascii=False)
        if not ctx.is_tool_enabled("gateway_receive_message"):
            return json.dumps({"ok": False, "error": {"code": "tool_disabled", "message": "tool is disabled"}}, ensure_ascii=False)
        if ctx.requires_confirmation("gateway_receive_message") and not confirm:
            return json.dumps({"ok": False, "error": {"code": "confirmation_required", "message": "This tool requires confirm=true"}}, ensure_ascii=False)

        # 输入校验
        if not channel_id or not channel_id.strip():
            return json.dumps({"ok": False, "error": {"code": "invalid_input", "message": "channel_id is required"}}, ensure_ascii=False)
        if not isinstance(raw_event, dict) or not raw_event:
            return json.dumps({"ok": False, "error": {"code": "invalid_input", "message": "raw_event must be a non-empty dict"}}, ensure_ascii=False)

        args = {"channel_id": channel_id, "raw_event": raw_event, "headers": headers, "remote_addr": remote_addr}
        try:
            result = await facade.receive_message(args)
            _audit(ctx, "gateway_receive_message", args, result)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            err = format_mcp_error(e)
            _audit(ctx, "gateway_receive_message", args, err)
            return json.dumps(err, ensure_ascii=False)

    @mcp_server.tool()
    async def gateway_send_message(
        channel_id: str,
        conversation_id: str,
        content: str,
        metadata: dict | None = None,
        confirm: bool = False,
    ) -> str:
        """直接向某个频道投递消息（高危操作）

        Args:
            confirm: 高危操作需显式确认 (confirm=true)
        """
        if not check_permission("gateway_send_message", _get_scopes(ctx)):
            return json.dumps({"ok": False, "error": {"code": "permission_denied", "message": "no permission"}}, ensure_ascii=False)
        if not ctx.is_tool_enabled("gateway_send_message"):
            return json.dumps({"ok": False, "error": {"code": "tool_disabled", "message": "tool is disabled by config"}}, ensure_ascii=False)
        if ctx.requires_confirmation("gateway_send_message") and not confirm:
            return json.dumps({"ok": False, "error": {"code": "confirmation_required", "message": "This tool requires confirm=true"}}, ensure_ascii=False)

        # 输入校验
        if not channel_id or not channel_id.strip():
            return json.dumps({"ok": False, "error": {"code": "invalid_input", "message": "channel_id is required"}}, ensure_ascii=False)
        if not conversation_id or not conversation_id.strip():
            return json.dumps({"ok": False, "error": {"code": "invalid_input", "message": "conversation_id is required"}}, ensure_ascii=False)
        if not content or not content.strip():
            return json.dumps({"ok": False, "error": {"code": "invalid_input", "message": "content is required"}}, ensure_ascii=False)

        args = {"channel_id": channel_id, "conversation_id": conversation_id, "content": content, "metadata": metadata}
        try:
            result = await facade.send_channel_message(
                channel_id=channel_id,
                conversation_id=conversation_id,
                content=content,
                metadata=metadata,
            )
            _audit(ctx, "gateway_send_message", args, result)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            err = format_mcp_error(e)
            _audit(ctx, "gateway_send_message", args, err)
            return json.dumps(err, ensure_ascii=False)

    @mcp_server.tool()
    async def gateway_submit_internal_task(
        task_kind: str,
        task_id: str,
        trigger_source: str = "mcp",
        metadata: dict | None = None,
        confirm: bool = False,
    ) -> str:
        """触发内部任务（心跳、工作流、定时任务等）

        注意：当前版本仅提交 noop 任务用于链路测试，后续版本将支持注册 handler。

        Args:
            confirm: 高危操作需显式确认 (confirm=true)
        """
        if not check_permission("gateway_submit_internal_task", _get_scopes(ctx)):
            return json.dumps({"ok": False, "error": {"code": "permission_denied", "message": "no permission"}}, ensure_ascii=False)
        if not ctx.is_tool_enabled("gateway_submit_internal_task"):
            return json.dumps({"ok": False, "error": {"code": "tool_disabled", "message": "tool is disabled"}}, ensure_ascii=False)
        if ctx.requires_confirmation("gateway_submit_internal_task") and not confirm:
            return json.dumps({"ok": False, "error": {"code": "confirmation_required", "message": "This tool requires confirm=true"}}, ensure_ascii=False)

        # 输入校验
        if not task_kind or not task_kind.strip():
            return json.dumps({"ok": False, "error": {"code": "invalid_input", "message": "task_kind is required"}}, ensure_ascii=False)
        if not task_id or not task_id.strip():
            return json.dumps({"ok": False, "error": {"code": "invalid_input", "message": "task_id is required"}}, ensure_ascii=False)

        args = {"task_kind": task_kind, "task_id": task_id, "trigger_source": trigger_source, "metadata": metadata}
        try:
            result = await facade.submit_internal_task(
                task_kind=task_kind,
                task_id=task_id,
                trigger_source=trigger_source,
                metadata=metadata,
            )
            _audit(ctx, "gateway_submit_internal_task", args, result)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            err = format_mcp_error(e)
            _audit(ctx, "gateway_submit_internal_task", args, err)
            return json.dumps(err, ensure_ascii=False)

    @mcp_server.tool()
    async def gateway_retry_dead_letter(item_id: str, confirm: bool = False) -> str:
        """重试死信队列中的某个任务（高危操作）

        Args:
            confirm: 高危操作需显式确认 (confirm=true)
        """
        if not check_permission("gateway_retry_dead_letter", _get_scopes(ctx)):
            return json.dumps({"ok": False, "error": {"code": "permission_denied", "message": "no permission"}}, ensure_ascii=False)
        if not ctx.is_tool_enabled("gateway_retry_dead_letter"):
            return json.dumps({"ok": False, "error": {"code": "tool_disabled", "message": "tool is disabled"}}, ensure_ascii=False)
        if ctx.requires_confirmation("gateway_retry_dead_letter") and not confirm:
            return json.dumps({"ok": False, "error": {"code": "confirmation_required", "message": "This tool requires confirm=true"}}, ensure_ascii=False)

        if not item_id or not item_id.strip():
            return json.dumps({"ok": False, "error": {"code": "invalid_input", "message": "item_id is required"}}, ensure_ascii=False)

        args = {"item_id": item_id}
        try:
            result = await facade.retry_dead_letter(item_id)
            _audit(ctx, "gateway_retry_dead_letter", args, result)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            err = format_mcp_error(e)
            _audit(ctx, "gateway_retry_dead_letter", args, err)
            return json.dumps(err, ensure_ascii=False)

    # ========================
    # 节点管理 Tools
    # ========================

    @mcp_server.tool()
    async def gateway_register_node(
        node_id: str,
        node_type: str = "worker",
        version: str = "",
        address: str = "",
        metadata: dict | None = None,
        confirm: bool = False,
    ) -> str:
        """注册节点（高危操作）

        Args:
            confirm: 高危操作需显式确认 (confirm=true)
        """
        if not check_permission("gateway_register_node", _get_scopes(ctx)):
            return json.dumps({"ok": False, "error": {"code": "permission_denied", "message": "no permission"}}, ensure_ascii=False)
        if ctx.requires_confirmation("gateway_register_node") and not confirm:
            return json.dumps({"ok": False, "error": {"code": "confirmation_required", "message": "This tool requires confirm=true"}}, ensure_ascii=False)

        if not node_id or not node_id.strip():
            return json.dumps({"ok": False, "error": {"code": "invalid_input", "message": "node_id is required"}}, ensure_ascii=False)

        args = {"node_id": node_id, "node_type": node_type, "version": version, "address": address}
        try:
            result = await facade.register_node(
                node_id=node_id,
                node_type=node_type,
                version=version,
                address=address,
                metadata=metadata,
            )
            _audit(ctx, "gateway_register_node", args, result)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            err = format_mcp_error(e)
            _audit(ctx, "gateway_register_node", args, err)
            return json.dumps(err, ensure_ascii=False)


def _get_scopes(ctx: MCPContext) -> list[str]:
    """获取当前上下文的权限列表

    stdio 模式不再自动注入 admin。
    需要 admin 权限时，通过配置 permissions.admin = true 显式开启。
    """
    default = list(ctx.config.get("permissions", {}).get("default_scopes", []))
    if ctx.config.get("permissions", {}).get("admin", False):
        default.append("admin")
    return list(set(default))


def _audit(ctx: MCPContext, tool_name: str, args: dict, result: dict) -> None:
    """记录审计日志"""
    audit_config = ctx.config.get("audit", {})
    if not audit_config.get("enabled", True):
        return

    entry = audit_log_entry(
        tool_name,
        args,
        result,
        redact_fields=audit_config.get("redact_fields"),
    )
    _log.info("[MCP Audit] %s", json.dumps(entry, ensure_ascii=False))
