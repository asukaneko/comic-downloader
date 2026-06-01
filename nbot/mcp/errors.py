"""MCP 统一错误包装

将 GatewayError 和其他异常转换为 MCP 可返回的结构化错误格式。
不直接返回 Python 异常字符串。
"""

import logging
from typing import Any

from nbot.gateway.errors import (
    DeliveryFailedError,
    DispatchFailedError,
    DuplicatedMessageError,
    GatewayError,
    InvalidSignatureError,
    InvalidTokenError,
    RateLimitedError,
    ReplayDetectedError,
    SecurityVerificationError,
    TimestampExpiredError,
    UnknownChannelError,
)

_log = logging.getLogger(__name__)

# GatewayError → MCP error code 映射
_ERROR_CODE_MAP: dict[type, str] = {
    UnknownChannelError: "unknown_channel",
    RateLimitedError: "rate_limited",
    DuplicatedMessageError: "duplicated",
    InvalidSignatureError: "invalid_signature",
    InvalidTokenError: "invalid_token",
    TimestampExpiredError: "timestamp_expired",
    ReplayDetectedError: "replay_detected",
    SecurityVerificationError: "security_error",
    DispatchFailedError: "dispatch_failed",
    DeliveryFailedError: "delivery_failed",
}


def format_mcp_error(
    error: Exception,
    *,
    trace_id: str = "",
) -> dict[str, Any]:
    """将异常转换为 MCP 结构化错误格式

    Args:
        error: 原始异常
        trace_id: 关联的 trace_id（如果有）

    Returns:
        结构化错误字典
    """
    if isinstance(error, GatewayError):
        code = _ERROR_CODE_MAP.get(type(error), error.code)
        stage = _infer_stage(code)
        retryable = _is_retryable(code)

        result: dict[str, Any] = {
            "ok": False,
            "error": {
                "code": code,
                "message": error.message,
                "stage": stage,
                "retryable": retryable,
            },
        }
        if trace_id:
            result["error"]["trace_id"] = trace_id
        return result

    # 未知异常
    _log.warning("[MCP] 未知异常: %s", str(error))
    result = {
        "ok": False,
        "error": {
            "code": "internal_error",
            "message": str(error),
            "stage": "unknown",
            "retryable": False,
        },
    }
    if trace_id:
        result["error"]["trace_id"] = trace_id
    return result


def _infer_stage(code: str) -> str:
    """根据错误码推断失败阶段"""
    stage_map = {
        "unknown_channel": "routing",
        "disabled_channel": "routing",
        "rate_limited": "rate_limit",
        "duplicated": "dedupe",
        "invalid_signature": "security",
        "invalid_token": "security",
        "timestamp_expired": "security",
        "replay_detected": "security",
        "security_error": "security",
        "parse_failed": "parse",
        "dispatch_failed": "dispatch",
        "delivery_failed": "delivery",
    }
    return stage_map.get(code, "unknown")


def _is_retryable(code: str) -> bool:
    """判断错误是否可重试"""
    non_retryable = {
        "unknown_channel",
        "disabled_channel",
        "invalid_signature",
        "invalid_token",
        "timestamp_expired",
        "replay_detected",
        "duplicated",
    }
    return code not in non_retryable
