"""Gateway 统一日志数据模型

定义日志类型、级别、阶段枚举和日志记录 dataclass。
"""

import json as _json
from dataclasses import dataclass
from enum import Enum
from typing import Any


class GatewayLogType(str, Enum):
    """日志类型"""

    GATEWAY_EVENT = "gateway_event"
    DELIVERY = "delivery"
    QUEUE = "queue"
    MCP_TOOL = "mcp_tool"
    MCP_RESOURCE = "mcp_resource"
    MCP_PROMPT = "mcp_prompt"
    SECURITY = "security"
    SYSTEM = "system"


class GatewayLogLevel(str, Enum):
    """日志级别"""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class GatewayLogStage(str, Enum):
    """日志阶段"""

    RECEIVED = "received"
    PREFLIGHT = "preflight"
    VALIDATION = "validation"
    CONFIRMATION = "confirmation"
    DISPATCH = "dispatch"
    DELIVERY = "delivery"
    QUEUE = "queue"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class GatewayLogRecord:
    """统一日志记录"""

    id: str
    trace_id: str | None
    source: str
    type: str
    level: str
    stage: str
    action: str
    status: str
    message: str

    tool_name: str | None = None
    channel_id: str | None = None
    conversation_id: str | None = None
    user_id: str | None = None
    message_id: str | None = None
    delivery_id: str | None = None
    queue_item_id: str | None = None
    node_id: str | None = None

    request_id: str | None = None
    parent_id: str | None = None

    metadata: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None

    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为可序列化字典"""
        result: dict[str, Any] = {
            "id": self.id,
            "source": self.source,
            "type": self.type,
            "level": self.level,
            "stage": self.stage,
            "action": self.action,
            "status": self.status,
            "message": self.message,
            "created_at": self.created_at,
        }
        for key in (
            "trace_id", "tool_name", "channel_id", "conversation_id",
            "user_id", "message_id", "delivery_id", "queue_item_id",
            "node_id", "request_id", "parent_id",
            "error_code", "error_message",
        ):
            val = getattr(self, key)
            if val is not None:
                result[key] = val
        if self.metadata:
            result["metadata"] = self.metadata
            # 前端兼容：提供 JSON 字符串格式
            result["metadata_json"] = _json.dumps(self.metadata, ensure_ascii=False)
        # 前端兼容：error 字段别名
        if self.error_message:
            result["error"] = self.error_message
        return result
