"""Gateway 统一日志模块

提供统一的日志记录、查询、聚合能力。
MCP 工具调用、Gateway 事件、投递记录等全部通过 GatewayLogService 写入。
"""

from nbot.gateway.logs.models import (
    GatewayLogLevel,
    GatewayLogRecord,
    GatewayLogStage,
    GatewayLogType,
)
from nbot.gateway.logs.redact import redact_content, redact_raw_event, redact_sensitive
from nbot.gateway.logs.service import GatewayLogService
from nbot.gateway.logs.sqlite_store import SQLiteGatewayLogStore
from nbot.gateway.logs.store import GatewayLogStore

__all__ = [
    "GatewayLogLevel",
    "GatewayLogRecord",
    "GatewayLogStage",
    "GatewayLogType",
    "GatewayLogService",
    "GatewayLogStore",
    "SQLiteGatewayLogStore",
    "redact_sensitive",
    "redact_content",
    "redact_raw_event",
]
