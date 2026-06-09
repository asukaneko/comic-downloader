import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from nbot.core.chat_models import ChatRequest, ChatResponse


@dataclass
class ChannelCapabilities:
    supports_stream: bool = False
    supports_progress_updates: bool = False
    supports_file_send: bool = False
    supports_stop: bool = False


@dataclass
class ChannelEnvelope:
    channel: str
    conversation_id: str
    user_id: str = ""
    sender: str = ""
    attachments: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseChannelAdapter:
    channel_name: str = "unknown"

    def get_capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities()

    def build_envelope(self, **kwargs) -> ChannelEnvelope:
        return ChannelEnvelope(channel=self.channel_name, **kwargs)

    def build_chat_request(
        self,
        *,
        conversation_id: str | None = None,
        content: str,
        sender: str = "",
        user_id: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
        parent_message_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "ChatRequest":
        from nbot.core.chat_models import ChatRequest

        normalized_content = self.normalize_inbound_message(content)
        normalized_attachments = self.normalize_attachments(attachments)
        envelope = self.build_envelope(
            conversation_id=conversation_id or "",
            user_id=str(user_id) if user_id is not None else "",
            sender=sender,
            attachments=normalized_attachments,
            metadata=dict(metadata or {}),
        )
        return ChatRequest(
            channel=envelope.channel,
            conversation_id=envelope.conversation_id,
            user_id=envelope.user_id or None,
            content=normalized_content,
            sender=envelope.sender,
            attachments=envelope.attachments,
            parent_message_id=parent_message_id,
            metadata=envelope.metadata,
        )

    def build_message(
        self,
        *,
        role: str,
        content: str,
        sender: str = "",
        conversation_id: str = "",
        attachments: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        message = {
            "id": str(uuid.uuid4()),
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "sender": sender,
            "source": source or self.channel_name,
        }
        if conversation_id:
            message["session_id"] = conversation_id
        if attachments:
            message["attachments"] = list(attachments)
        if metadata:
            message.update(metadata)
        return message

    def build_manager_payload(
        self,
        *,
        role: str,
        content: str,
        sender: str = "",
        conversation_id: str = "",
        attachments: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        source: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        payload = {
            "role": role,
            "content": content,
            "sender": sender,
            "source": source or self.channel_name,
            "session_id": conversation_id,
        }
        if attachments:
            payload["attachments"] = list(attachments)
        if metadata:
            payload["metadata"] = dict(metadata)
        # 将 extra 参数（如 user_id, group_id 等）合并到 metadata
        if extra:
            payload.setdefault("metadata", {})
            payload["metadata"].update(extra)
        return payload

    def build_manager_payload_from_message(
        self,
        message: dict[str, Any],
        *,
        default_role: str,
        default_content: str,
        default_sender: str = "",
        default_conversation_id: str = "",
        default_source: str | None = None,
        metadata: dict[str, Any] | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        merged_metadata = dict(message.get("metadata") or {})
        if metadata:
            merged_metadata.update(metadata)
        return self.build_manager_payload(
            role=message.get("role", default_role),
            content=message.get("content", default_content),
            sender=message.get("sender", default_sender),
            conversation_id=message.get("session_id", default_conversation_id),
            attachments=message.get("attachments"),
            metadata=merged_metadata,
            source=message.get("source", default_source or self.channel_name),
            **extra,
        )

    def build_assistant_message(
        self,
        chat_response: "ChatResponse",
        *,
        conversation_id: str,
        sender: str = "AI",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        message = chat_response.to_assistant_message(sender=sender)
        message_metadata = dict(metadata or {})
        for key in ("can_continue", "tool_call_history", "error"):
            if key in message:
                message_metadata[key] = message[key]

        channel_message = self.build_message(
            role=message.get("role", "assistant"),
            content=message.get("content", ""),
            sender=message.get("sender", sender),
            conversation_id=conversation_id,
            metadata=message_metadata,
        )
        channel_message["id"] = message.get("id") or channel_message["id"]
        channel_message["sender"] = message.get("sender") or sender or channel_message["sender"]
        channel_message["timestamp"] = message.get("timestamp") or channel_message["timestamp"]
        return channel_message

    def normalize_inbound_message(self, content: str) -> str:
        result = (content or "").strip()
        # 非 Web 频道：剥离默认删除标记 <||>
        if self.channel_name != "web" and result:
            from nbot.message_filter import MessageFilter

            result = MessageFilter.strip_default_markers(result)
        return result

    def normalize_attachments(
        self, attachments: list[dict[str, Any]] | None = None
    ) -> list[dict[str, Any]]:
        return list(attachments or [])

    def parse_event(self, raw_event: dict[str, Any]) -> dict[str, Any] | None:
        """解析平台原始事件为 Gateway 统一格式

        子类应覆盖此方法以支持各自平台的事件格式。
        返回字典包含以下字段（供 build_chat_request 使用）：
          - conversation_id: 会话 ID
          - user_id: 用户 ID
          - sender: 发送者名称
          - content: 消息文本内容
          - message_id: 平台消息 ID（用于去重）
          - attachments: 附件列表
          - metadata: 平台特定元数据

        返回 None 表示忽略该事件（非消息事件等）。
        """
        return None
