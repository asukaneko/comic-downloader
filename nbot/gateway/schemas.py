"""Gateway 统一数据结构定义"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GatewayEvent:
    """Gateway 内部统一事件格式

    比 ChatRequest 更靠近「入口事件」，
    保留 raw_event、headers、remote_addr 等边界信息。
    """

    trace_id: str = ""
    channel_id: str = ""
    event_type: str = "message"
    raw_event: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    remote_addr: str = ""
    received_at: str = ""

    # 解析后的通用字段
    message_id: str | None = None
    conversation_id: str | None = None
    user_id: str | None = None
    content: str = ""
    sender: str = ""
    attachments: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "channel_id": self.channel_id,
            "event_type": self.event_type,
            "message_id": self.message_id,
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "content": self.content,
            "sender": self.sender,
            "remote_addr": self.remote_addr,
            "received_at": self.received_at,
        }


@dataclass
class GatewayResult:
    """Gateway 处理结果，统一返回给调用方"""

    ok: bool = True
    trace_id: str = ""
    channel_id: str = ""
    conversation_id: str = ""
    status: str = "ok"
    ignored: bool = False
    duplicated: bool = False
    queued: bool = False
    error: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "ok": self.ok,
            "trace_id": self.trace_id,
            "channel_id": self.channel_id,
            "status": self.status,
        }
        if self.conversation_id:
            result["conversation_id"] = self.conversation_id
        if self.ignored:
            result["ignored"] = True
        if self.duplicated:
            result["duplicated"] = True
        if self.queued:
            result["queued"] = True
        if self.error:
            result["error"] = self.error
        if self.data:
            result["data"] = self.data
        return result


@dataclass
class DeliveryRequest:
    """回复投递请求"""

    trace_id: str = ""
    channel_id: str = ""
    conversation_id: str = ""
    content: str = ""
    reply_to_message_id: str | None = None
    attachments: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
