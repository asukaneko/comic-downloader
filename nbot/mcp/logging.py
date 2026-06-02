"""MCP 工具调用日志

将 MCP 工具调用的完整生命周期写入 Gateway 统一日志 **和** Python logging。
不替代现有的 _audit()，而是作为 Gateway Log 的写入层。

每条 MCP 工具调用同时产生：
1. Python logging（写入 bot.log / mcp.log） — 方便运维实时排查
2. GatewayLogService record（写入 gateway.db） — 方便前端查询和 trace 聚合
"""

import json
import logging
import time
from typing import Any

_log = logging.getLogger(__name__)

# 这些工具成功时不记录日志，避免"日志记录日志"的噪音循环
_NOISY_TOOLS: set[str] = {"gateway_query_logs"}

# 脱敏键集合（不区分大小写）
_SENSITIVE_KEYS: frozenset[str] = frozenset({
    "token", "secret", "password", "authorization", "api_key",
})

# content 预览长度上限
_CONTENT_PREVIEW_LEN: int = 200


class MCPToolLogger:
    """MCP 工具调用日志记录器

    记录 MCP 工具调用的各阶段（同时写入 Python log + gateway_logs）：
    - called:               工具被调用
    - denied:               权限拒绝
    - confirmation_required: 需要确认
    - validation_failed:    输入校验失败
    - completed:            执行成功
    - failed:               执行失败
    """

    def __init__(self, ctx: Any):
        self._log_service = None
        if hasattr(ctx, "gateway") and hasattr(ctx.gateway, "log_service"):
            self._log_service = ctx.gateway.log_service
        self._started_at: float = time.monotonic()

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _record(self, **kwargs: Any) -> None:
        """写入 Gateway 统一日志（SQLite，如果 log_service 可用）"""
        if not self._log_service:
            return
        try:
            self._log_service.record(**kwargs)
        except Exception as e:
            _log.warning("[MCPLog] gateway log write failed: %s", e)

    def _elapsed_ms(self) -> float:
        """返回自 logger 创建以来的毫秒数"""
        return round((time.monotonic() - self._started_at) * 1000, 1)

    # ------------------------------------------------------------------
    # 生命周期记录
    # ------------------------------------------------------------------

    def called(self, tool_name: str, args: dict[str, Any]) -> None:
        """记录工具调用开始"""
        safe = _safe_args(args)
        args_preview = _format_args_for_log(safe)

        _log.info(
            "[MCP] ▶ tool=%s args=%s",
            tool_name,
            args_preview,
        )

        self._record(
            source="mcp",
            type="mcp_tool",
            level="info",
            stage="called",
            action=tool_name,
            status="pending",
            message=f"MCP tool called: {tool_name}",
            tool_name=tool_name,
            metadata={
                "args": safe,
                "args_preview": args_preview,
            },
        )

    def denied(self, tool_name: str, reason: str, args: dict[str, Any]) -> None:
        """记录权限拒绝"""
        safe = _safe_args(args)
        args_preview = _format_args_for_log(safe)

        _log.warning(
            "[MCP] ✕ DENIED tool=%s reason=%s args=%s",
            tool_name,
            reason,
            args_preview,
        )

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
            metadata={
                "args": safe,
                "args_preview": args_preview,
            },
        )

    def confirmation_required(self, tool_name: str, args: dict[str, Any]) -> None:
        """记录需要确认"""
        safe = _safe_args(args)

        _log.warning(
            "[MCP] ⚠ CONFIRM_REQUIRED tool=%s args=%s",
            tool_name,
            _format_args_for_log(safe),
        )

        self._record(
            source="mcp",
            type="security",
            level="info",
            stage="confirmation",
            action=tool_name,
            status="confirmation_required",
            message=f"MCP tool requires confirmation: {tool_name}",
            tool_name=tool_name,
            metadata={"args": safe},
        )

    def validation_failed(
        self,
        tool_name: str,
        args: dict[str, Any],
        error: dict[str, Any],
    ) -> None:
        """记录输入校验失败"""
        safe = _safe_args(args)
        err_info = error.get("error", {}) if isinstance(error.get("error"), dict) else {}
        err_code = err_info.get("code", "invalid_input")
        err_msg = err_info.get("message", "")

        _log.warning(
            "[MCP] ✕ VALIDATION tool=%s code=%s detail=%s args=%s",
            tool_name,
            err_code,
            err_msg,
            _format_args_for_log(safe),
        )

        self._record(
            source="mcp",
            type="mcp_tool",
            level="warning",
            stage="validation",
            action=tool_name,
            status="failed",
            message=f"MCP tool validation failed: {tool_name} — {err_msg}",
            tool_name=tool_name,
            error_code=err_code,
            error_message=err_msg,
            metadata={
                "args": safe,
                "validation_error": err_info,
            },
        )

    def completed(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: dict[str, Any],
        trace_id: str | None = None,
    ) -> None:
        """记录执行成功（噪音工具跳过）"""
        elapsed = self._elapsed_ms()
        if tool_name in _NOISY_TOOLS:
            return

        if not trace_id:
            trace_id = result.get("trace_id")

        result_summary = _build_result_summary(result)
        result_keys = list(result.keys()) if isinstance(result, dict) else []
        safe = _safe_args(args)

        _log.info(
            "[MCP] ✓ tool=%s elapsed=%sms summary=%s result_keys=%s trace=%s",
            tool_name,
            elapsed,
            result_summary,
            result_keys,
            trace_id or "-",
        )

        self._record(
            source="mcp",
            type="mcp_tool",
            level="info",
            stage="completed",
            action=tool_name,
            status="success",
            message=f"MCP tool completed: {tool_name} ({elapsed}ms)",
            tool_name=tool_name,
            trace_id=trace_id,
            metadata={
                "args": safe,
                "result_summary": result_summary,
                "result_keys": result_keys,
                "elapsed_ms": elapsed,
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
        elapsed = self._elapsed_ms()
        if not trace_id:
            trace_id = error.get("trace_id")

        err_info = error.get("error", {}) if isinstance(error.get("error"), dict) else {}
        err_code = err_info.get("code", "unknown")
        err_msg = err_info.get("message", str(error))
        safe = _safe_args(args)

        _log.error(
            "[MCP] ✕ FAILED tool=%s elapsed=%sms code=%s error=%s trace=%s args=%s",
            tool_name,
            elapsed,
            err_code,
            err_msg,
            trace_id or "-",
            _format_args_for_log(safe),
        )

        self._record(
            source="mcp",
            type="mcp_tool",
            level="error",
            stage="failed",
            action=tool_name,
            status="failed",
            message=f"MCP tool failed: {tool_name} ({elapsed}ms) — {err_msg}",
            tool_name=tool_name,
            trace_id=trace_id,
            error_code=err_code,
            error_message=err_msg,
            metadata={
                "args": safe,
                "elapsed_ms": elapsed,
                "error_detail": err_info,
            },
        )


# ======================================================================
# 参数脱敏
# ======================================================================

def _safe_args(args: dict[str, Any]) -> dict[str, Any]:
    """脱敏参数

    - token/secret/password/authorization/api_key → ***
    - headers → 保留 key 列表，不存值
    - raw_event → 保留 keys、size + 内容截断预览
    - content → 保留较长 preview + length
    - 其他字段原样保留
    """
    result: dict[str, Any] = {}
    for key, value in args.items():
        lower_key = key.lower()
        if lower_key in _SENSITIVE_KEYS:
            result[key] = "***"
        elif lower_key == "headers" and isinstance(value, dict):
            result[key] = {"header_keys": list(value.keys()), "_redacted": True}
        elif lower_key == "raw_event" and isinstance(value, dict):
            preview_str = _truncate(str(value), 300)
            result[key] = {
                "keys": list(value.keys()),
                "size": len(str(value)),
                "preview": preview_str,
            }
        elif lower_key == "content" and isinstance(value, str):
            result[key] = {
                "preview": value[:_CONTENT_PREVIEW_LEN],
                "length": len(value),
            }
        elif isinstance(value, str) and len(value) > 500:
            result[key] = {"preview": value[:200], "length": len(value)}
        else:
            result[key] = value
    return result


def _format_args_for_log(safe_args: dict[str, Any]) -> str:
    """将脱敏后的 args 格式化为一行紧凑字符串（用于 Python log）

    省略过于冗长的字段，只保留 key=value 形式。
    """
    parts: list[str] = []
    for key, value in safe_args.items():
        if isinstance(value, str) and len(value) > 120:
            parts.append(f"{key}={value[:100]}…({len(value)}c)")
        elif isinstance(value, dict):
            # 对字典值，显示 key 列表或 preview
            if "_redacted" in value:
                parts.append(f"{key}=[{','.join(value.get('header_keys', []))}]")
            elif "preview" in value and "length" in value:
                preview = value["preview"]
                if isinstance(preview, str) and len(preview) > 80:
                    preview = preview[:80] + "…"
                parts.append(f"{key}={preview}({value['length']}c)")
            elif "keys" in value:
                parts.append(f"{key}={value['keys']}")
            else:
                short = json.dumps(value, ensure_ascii=False)
                if len(short) > 120:
                    short = short[:100] + "…"
                parts.append(f"{key}={short}")
        elif isinstance(value, list):
            parts.append(f"{key}=[{len(value)} items]")
        else:
            s = str(value)
            if len(s) > 120:
                s = s[:100] + "…"
            parts.append(f"{key}={s}")
    return " ".join(parts) if parts else "{}"


# ======================================================================
# 结果摘要
# ======================================================================

def _build_result_summary(result: dict[str, Any]) -> str:
    """构建结果摘要（比原版更详细）

    保留 ok/status/error 等核心字段，
    同时提取 count/data/items 等数据维度信息。
    """
    if not result:
        return "empty result"

    ok = result.get("ok")
    status = result.get("status", "")

    if ok is False:
        error = result.get("error", {})
        if isinstance(error, dict):
            return f"error: {error.get('message', 'unknown')}"
        return f"error: {error}"

    parts: list[str] = []
    if ok is True:
        parts.append("ok")
    if status:
        parts.append(f"status={status}")

    # 从 summary 子字典提取计数
    for key in ("events_count", "deliveries_count", "mcp_logs_count"):
        val = result.get("summary", {}).get(key)
        if val:
            parts.append(f"{key}={val}")

    # 提取顶层数据计数
    for key in ("count", "total", "items_count"):
        val = result.get(key)
        if isinstance(val, int) and val > 0:
            parts.append(f"{key}={val}")

    # items 数组长度
    items = result.get("items")
    if isinstance(items, list) and items:
        parts.append(f"items={len(items)}")

    # data 中的额外信息
    data = result.get("data")
    if isinstance(data, dict):
        for dk in ("response_content", "result"):
            dv = data.get(dk)
            if isinstance(dv, str) and dv:
                parts.append(f"{dk}={dv[:60]}{'…' if len(dv) > 60 else ''}")

    return ", ".join(parts) if parts else "success"


# ======================================================================
# 工具函数
# ======================================================================

def _truncate(text: str, max_len: int) -> str:
    """截断文本到 max_len，超出部分用 … 替代"""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"
