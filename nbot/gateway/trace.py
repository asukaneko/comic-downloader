"""Trace ID 生成与日志上下文管理"""

import logging
import time
import uuid
from contextlib import contextmanager

_log = logging.getLogger(__name__)

# 当前线程的 trace_id 上下文
_trace_context: str | None = None


def new_trace_id() -> str:
    """生成新的 trace_id

    格式：gw_{YYYYMMDD}_{HHMMSS}_{8位随机hex}
    示例：gw_20260525_153000_a1b2c3d4
    """
    ts = time.strftime("%Y%m%d_%H%M%S")
    rand = uuid.uuid4().hex[:8]
    return f"gw_{ts}_{rand}"


def get_current_trace_id() -> str:
    """获取当前上下文中的 trace_id"""
    return _trace_context or ""


def set_trace_id(trace_id: str) -> None:
    """设置当前上下文的 trace_id"""
    global _trace_context
    _trace_context = trace_id


def clear_trace_id() -> None:
    """清除当前上下文的 trace_id"""
    global _trace_context
    _trace_context = None


@contextmanager
def trace_context(trace_id: str):
    """Trace 上下文管理器，用于在代码块中设置和自动清理 trace_id"""
    old = _trace_context
    try:
        set_trace_id(trace_id)
        _log.debug("[Trace] 进入上下文 trace_id=%s", trace_id)
        yield trace_id
    finally:
        set_trace_id(old or "")
        _log.debug("[Trace] 退出上下文 trace_id=%s", trace_id)


class TraceFactory:
    """Trace ID 工厂，支持自定义前缀"""

    def __init__(self, prefix: str = "gw"):
        self.prefix = prefix

    def new_trace_id(self) -> str:
        ts = time.strftime("%Y%m%d_%H%M%S")
        rand = uuid.uuid4().hex[:8]
        return f"{self.prefix}_{ts}_{rand}"
