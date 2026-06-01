"""MCP 工具调用日志

将 MCP 工具调用的完整生命周期写入 Gateway 统一日志。
不替代现有的 _audit()，而是作为 Gateway Log 的写入层。
"""

import logging
from typing import Any

_log = logging.getLogger(__name__)


class MCPToolLogger:
    """MCP 工具调用日志记录器

    记录 MCP 工具调用的各阶段：
    - called: 工具被调用
    - denied: 权限拒绝
    - confirmation_required: 需要确认
    - validation_failed: 输入校验失败
    - completed: 执行成功
    - failed: 执行失败
    """

    def __init__(self, ctx: Any):
        self._log_service = None
        if hasattr(ctx, "gateway") and hasattr(ctx.gateway, "log_service"):
            self._log_service = ctx.gateway.log_service

    def _record(self, **kwargs: Any) -> None:
        """写入日志（如果 log_service 可用）"""
        if not self._log_service:
            return
        try:
            self._log_service.record(**kwargs)
        except Exception as e:
            _log.warning("[MCPLog] 写入日志失败: %s", e)

    def called(self, tool_name: str, args: dict[str, Any]) -> None:
        """记录工具调用开始"""
        self._record(
            source="mcp",
            type="mcp_tool",
            level="info",
            stage="called",
            action=tool_name,
            status="pending",
            message=f"MCP tool called: {tool_name}",
            tool_name=tool_name,
            metadata=_safe_args(args),
        )

    def denied(self, tool_name: str, reason: str, args: dict[str, Any]) -> None:
        """记录权限拒绝"""
        self._record(
            source="mcp",
            type="security",
            level="warning",
            stage="preflight",
            action=tool_name,
            status="denied",
            message=f"MCP tool denied: {tool_name} ({reason})",
            tool_name=tool_name,
            error_code="permission_denied",
            error_message=reason,
            metadata=_safe_args(args),
        )

    def confirmation_required(self, tool_name: str, args: dict[str, Any]) -> None:
        """记录需要确认"""
        self._record(
            source="mcp",
            type="security",
            level="info",
            stage="confirmation",
            action=tool_name,
            status="confirmation_required",
            message=f"MCP tool requires confirmation: {tool_name}",
            tool_name=tool_name,
            metadata=_safe_args(args),
        )

    def validation_failed(
        self,
        tool_name: str,
        args: dict[str, Any],
        error: dict[str, Any],
    ) -> None:
        """记录输入校验失败"""
        self._record(
            source="mcp",
            type="mcp_tool",
            level="warning",
            stage="validation",
            action=tool_name,
            status="failed",
            message=f"MCP tool validation failed: {tool_name}",
            tool_name=tool_name,
            error_code=error.get("error", {}).get("code", "invalid_input"),
            error_message=error.get("error", {}).get("message", ""),
            metadata=_safe_args(args),
        )

    def completed(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: dict[str, Any],
        trace_id: str | None = None,
    ) -> None:
        """记录执行成功"""
        if not trace_id:
            trace_id = result.get("trace_id")

        result_summary = _build_result_summary(result)

        self._record(
            source="mcp",
            type="mcp_tool",
            level="info",
            stage="completed",
            action=tool_name,
            status="success",
            message=f"MCP tool completed: {tool_name}",
            tool_name=tool_name,
            trace_id=trace_id,
            metadata={
                "args": _safe_args(args),
                "result_summary": result_summary,
            },
        )

    def failed(
        self,
        tool_name: str,
        args: dict[str, Any],
        error: dict[str, Any],
        trace_id: str | None = None,
    ) -> None:
        """记录执行失败"""
        if not trace_id:
            trace_id = error.get("trace_id")

        self._record(
            source="mcp",
            type="mcp_tool",
            level="error",
            stage="failed",
            action=tool_name,
            status="failed",
            message=f"MCP tool failed: {tool_name}",
            tool_name=tool_name,
            trace_id=trace_id,
            error_code=error.get("error", {}).get("code", "unknown"),
            error_message=error.get("error", {}).get("message", str(error)),
            metadata=_safe_args(args),
        )


def _safe_args(args: dict[str, Any]) -> dict[str, Any]:
    """脱敏参数"""
    sensitive_keys = {"token", "secret", "password", "authorization", "api_key", "headers"}
    result: dict[str, Any] = {}
    for key, value in args.items():
        lower_key = key.lower()
        if lower_key in sensitive_keys:
            result[key] = "***"
        elif lower_key == "raw_event" and isinstance(value, dict):
            result[key] = {"keys": list(value.keys()), "size": len(str(value))}
        elif lower_key == "content" and isinstance(value, str) and len(value) > 100:
            result[key] = value[:100] + "..."
        else:
            result[key] = value
    return result


def _build_result_summary(result: dict[str, Any]) -> str:
    """构建结果摘要"""
    if not result:
        return "empty result"

    ok = result.get("ok")
    status = result.get("status", "")

    if ok is False:
        error = result.get("error", {})
        if isinstance(error, dict):
            return f"error: {error.get('message', 'unknown')}"
        return f"error: {error}"

    parts = []
    if ok is True:
        parts.append("ok")
    if status:
        parts.append(f"status={status}")

    for key in ("events_count", "deliveries_count", "mcp_logs_count"):
        val = result.get("summary", {}).get(key)
        if val:
            parts.append(f"{key}={val}")

    return ", ".join(parts) if parts else "success"
