"""MCP 权限模型

复用 Gateway 原有 PermissionScope，不在 MCP 层另起一套权限系统。

权限分级：
  只读:   gateway.read, events.query, queue.read, node.read
  操作:   events.publish, channels.send, worker.manage
  管理:   gateway.manage, queue.manage, node.manage
  超级管理: admin
"""

from typing import Any

# Tool → 所需权限映射
TOOL_PERMISSIONS: dict[str, str] = {
    "gateway_get_status": "gateway.read",
    "gateway_get_stats": "gateway.read",
    "gateway_query_trace": "events.query",
    "gateway_query_events": "events.query",
    "gateway_query_deliveries": "events.query",
    "gateway_get_queue_stats": "queue.read",
    "gateway_list_nodes": "node.read",
    "gateway_get_node": "node.read",
    # 操作型
    "gateway_receive_message": "events.publish",
    "gateway_send_message": "channels.send",
    "gateway_submit_internal_task": "worker.manage",
    "gateway_retry_dead_letter": "queue.manage",
    # 节点管理
    "gateway_register_node": "node.register",
    "gateway_create_pairing": "node.register",
    "gateway_approve_pairing": "node.manage",
}

# 高危工具列表（需要 audit + 确认）
HIGH_RISK_TOOLS: set[str] = {
    "gateway_send_message",
    "gateway_receive_message",
    "gateway_retry_dead_letter",
    "gateway_submit_internal_task",
    "gateway_approve_pairing",
    "gateway_register_node",
}

# 权限等级定义
SCOPE_LEVELS: dict[str, int] = {
    "gateway.read": 1,
    "events.query": 1,
    "queue.read": 1,
    "node.read": 1,
    "events.publish": 2,
    "channels.send": 2,
    "worker.manage": 2,
    "node.register": 2,
    "gateway.manage": 3,
    "queue.manage": 3,
    "node.manage": 3,
    "admin": 4,
}


def get_required_permission(tool_name: str) -> str | None:
    """获取工具所需的权限"""
    return TOOL_PERMISSIONS.get(tool_name)


def is_high_risk(tool_name: str) -> bool:
    """判断工具是否为高危操作"""
    return tool_name in HIGH_RISK_TOOLS


def check_permission(
    tool_name: str,
    granted_scopes: list[str],
) -> bool:
    """检查是否具有调用指定工具的权限

    Args:
        tool_name: 工具名称
        granted_scopes: 已授权的权限列表

    Returns:
        True 表示有权限
    """
    required = get_required_permission(tool_name)
    if required is None:
        return True  # 未映射的工具默认允许

    if "admin" in granted_scopes:
        return True

    return required in granted_scopes


def audit_log_entry(
    tool_name: str,
    args: dict[str, Any],
    result: dict[str, Any],
    *,
    redact_fields: list[str] | None = None,
) -> dict[str, Any]:
    """生成审计日志条目

    Args:
        tool_name: 工具名称
        args: 调用参数
        result: 调用结果
        redact_fields: 需要脱敏的字段列表

    Returns:
        审计日志字典
    """
    import datetime

    redact = set(redact_fields or ["token", "secret", "password", "authorization"])

    def _redact(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {
                k: "***" if k.lower() in redact else _redact(v)
                for k, v in obj.items()
            }
        if isinstance(obj, list):
            return [_redact(item) for item in obj]
        return obj

    return {
        "timestamp": datetime.datetime.now().isoformat(),
        "tool": tool_name,
        "args": _redact(args),
        "ok": result.get("ok", False),
        "is_high_risk": is_high_risk(tool_name),
    }
