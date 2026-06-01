"""MCP Gateway Tools

注册所有 Gateway 相关的 MCP Tools。
每个 Tool 对应一个 GatewayFacade 方法调用。

安全流程（每个操作型工具统一走）：
  1. 权限检查 (check_permission)
  2. 工具启用检查 (is_tool_enabled)
  3. 高危确认检查 (requires_confirmation + confirm 参数)
  4. 输入校验 (Pydantic Schema)
  5. 执行 + 审计
"""

import json
import logging
from typing import Any

from pydantic import ValidationError

from nbot.mcp.context import MCPContext
from nbot.mcp.errors import format_mcp_error
from nbot.mcp.permissions import audit_log_entry, check_permission
from nbot.mcp.schemas import (
    GetNodeInput,
    ListNodesInput,
    QueryDeliveriesInput,
    QueryEventsInput,
    QueryTraceInput,
    ReceiveMessageInput,
    RegisterNodeInput,
    RetryDeadLetterInput,
    SendMessageInput,
    SubmitInternalTaskInput,
)

_log = logging.getLogger(__name__)


# ========================
# 公共 Guard
# ========================


def _preflight(
    ctx: MCPContext,
    tool_name: str,
    confirm: bool = False,
) -> dict[str, Any] | None:
    """操作型工具的统一流程守卫

    按顺序检查：权限 → 工具启用 → 高危确认。
    返回 None 表示通过，返回 dict 表示应直接返回错误。
    """
    if not check_permission(tool_name, _get_scopes(ctx)):
        return {"ok": False, "error": {"code": "permission_denied", "message": "no permission"}}
    if not ctx.is_tool_enabled(tool_name):
        return {"ok": False, "error": {"code": "tool_disabled", "message": f"{tool_name} is disabled"}}
    if ctx.requires_confirmation(tool_name) and not confirm:
        return {
            "ok": False,
            "error": {
                "code": "confirmation_required",
                "message": f"{tool_name} requires confirm=true",
                "tool": tool_name,
            },
        }
    return None


def _validate_input(schema_class: type, **kwargs: Any) -> dict[str, Any] | None:
    """用 Pydantic Schema 校验输入

    返回 None 表示通过，返回 dict 表示校验失败的错误。
    """
    try:
        schema_class(**kwargs)
        return None
    except ValidationError as e:
        first_error = e.errors()[0]
        field = " → ".join(str(loc) for loc in first_error["loc"])
        return {
            "ok": False,
            "error": {
                "code": "invalid_input",
                "message": f"{field}: {first_error['msg']}",
            },
        }


def _err_json(err: dict[str, Any]) -> str:
    """统一 JSON 序列化错误返回"""
    return json.dumps(err, ensure_ascii=False)


# ========================
# Tool 注册
# ========================


def register_gateway_tools(mcp_server: Any, ctx: MCPContext) -> None:
    """注册所有 Gateway MCP Tools"""
    facade = ctx.facade

    # ========================
    # 只读 Tools（不需要 preflight）
    # ========================

    @mcp_server.tool()
    async def gateway_get_status() -> str:
        """查看 Gateway 健康状态"""
        try:
            result = await facade.get_status()
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return _err_json(format_mcp_error(e))

    @mcp_server.tool()
    async def gateway_get_stats() -> str:
        """查看事件、投递、去重、队列统计"""
        try:
            result = await facade.get_stats()
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return _err_json(format_mcp_error(e))

    @mcp_server.tool()
    async def gateway_query_trace(trace_id: str) -> str:
        """根据 trace_id 查询完整事件链路"""
        err = _preflight(ctx, "gateway_query_trace")
        if err:
            return _err_json(err)
        err = _validate_input(QueryTraceInput, trace_id=trace_id)
        if err:
            return _err_json(err)
        try:
            result = await facade.query_trace(trace_id)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return _err_json(format_mcp_error(e, trace_id=trace_id))

    @mcp_server.tool()
    async def gateway_query_events(
        channel_id: str = "",
        status: str = "",
        event_type: str = "",
        limit: int = 50,
    ) -> str:
        """按条件查询事件历史"""
        err = _preflight(ctx, "gateway_query_events")
        if err:
            return _err_json(err)
        err = _validate_input(QueryEventsInput, channel_id=channel_id, status=status, event_type=event_type, limit=limit)
        if err:
            return _err_json(err)
        try:
            result = await facade.query_events(
                channel_id=channel_id,
                status=status,
                event_type=event_type,
                limit=limit,
            )
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return _err_json(format_mcp_error(e))

    @mcp_server.tool()
    async def gateway_query_deliveries(
        trace_id: str = "",
        channel_id: str = "",
        status: str = "",
        limit: int = 20,
    ) -> str:
        """查询回复投递记录"""
        err = _preflight(ctx, "gateway_query_deliveries")
        if err:
            return _err_json(err)
        err = _validate_input(QueryDeliveriesInput, trace_id=trace_id, channel_id=channel_id, status=status, limit=limit)
        if err:
            return _err_json(err)
        try:
            result = await facade.query_deliveries(
                trace_id=trace_id,
                channel_id=channel_id,
                status=status,
                limit=limit,
            )
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return _err_json(format_mcp_error(e))

    @mcp_server.tool()
    async def gateway_get_queue_stats() -> str:
        """查看异步队列状态"""
        err = _preflight(ctx, "gateway_get_queue_stats")
        if err:
            return _err_json(err)
        try:
            result = await facade.get_queue_stats()
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return _err_json(format_mcp_error(e))

    @mcp_server.tool()
    async def gateway_list_nodes(
        node_type: str = "",
        status: str = "",
    ) -> str:
        """列出所有节点"""
        err = _preflight(ctx, "gateway_list_nodes")
        if err:
            return _err_json(err)
        try:
            result = await facade.list_nodes(node_type=node_type, status=status)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return _err_json(format_mcp_error(e))

    @mcp_server.tool()
    async def gateway_get_node(node_id: str) -> str:
        """获取节点详情"""
        err = _preflight(ctx, "gateway_get_node")
        if err:
            return _err_json(err)
        err = _validate_input(GetNodeInput, node_id=node_id)
        if err:
            return _err_json(err)
        try:
            result = await facade.get_node(node_id)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return _err_json(format_mcp_error(e))

    # ========================
    # 操作型 Tools（需要 preflight + 确认 + 校验）
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
        err = _preflight(ctx, "gateway_receive_message", confirm)
        if err:
            return _err_json(err)
        err = _validate_input(
            ReceiveMessageInput,
            channel_id=channel_id,
            raw_event=raw_event,
            headers=headers,
            remote_addr=remote_addr,
        )
        if err:
            return _err_json(err)

        args = {"channel_id": channel_id, "raw_event": raw_event, "headers": headers, "remote_addr": remote_addr}
        try:
            result = await facade.receive_message(args)
            _audit(ctx, "gateway_receive_message", args, result)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            err = format_mcp_error(e)
            _audit(ctx, "gateway_receive_message", args, err)
            return _err_json(err)

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
        err = _preflight(ctx, "gateway_send_message", confirm)
        if err:
            return _err_json(err)
        err = _validate_input(
            SendMessageInput,
            channel_id=channel_id,
            conversation_id=conversation_id,
            content=content,
            metadata=metadata,
        )
        if err:
            return _err_json(err)

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
            return _err_json(err)

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
        err = _preflight(ctx, "gateway_submit_internal_task", confirm)
        if err:
            return _err_json(err)
        err = _validate_input(
            SubmitInternalTaskInput,
            task_kind=task_kind,
            task_id=task_id,
            trigger_source=trigger_source,
            metadata=metadata,
        )
        if err:
            return _err_json(err)

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
            return _err_json(err)

    @mcp_server.tool()
    async def gateway_retry_dead_letter(item_id: str, confirm: bool = False) -> str:
        """重试死信队列中的某个任务（高危操作）

        Args:
            confirm: 高危操作需显式确认 (confirm=true)
        """
        err = _preflight(ctx, "gateway_retry_dead_letter", confirm)
        if err:
            return _err_json(err)
        err = _validate_input(RetryDeadLetterInput, item_id=item_id)
        if err:
            return _err_json(err)

        args = {"item_id": item_id}
        try:
            result = await facade.retry_dead_letter(item_id)
            _audit(ctx, "gateway_retry_dead_letter", args, result)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            err = format_mcp_error(e)
            _audit(ctx, "gateway_retry_dead_letter", args, err)
            return _err_json(err)

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
        err = _preflight(ctx, "gateway_register_node", confirm)
        if err:
            return _err_json(err)
        err = _validate_input(
            RegisterNodeInput,
            node_id=node_id,
            node_type=node_type,
            version=version,
            address=address,
            metadata=metadata,
        )
        if err:
            return _err_json(err)

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
            return _err_json(err)


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
