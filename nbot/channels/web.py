from typing import Any

from nbot.channels.base import BaseChannelAdapter, ChannelCapabilities, ChannelEnvelope


class WebChannelAdapter(BaseChannelAdapter):
    """Web 前端频道适配器"""

    channel_name = "web"

    def get_capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            supports_stream=True,
            supports_progress_updates=True,
            supports_file_send=True,
            supports_stop=True,
        )

    def build_envelope(self, **kwargs) -> ChannelEnvelope:
        metadata = dict(kwargs.get("metadata") or {})
        return ChannelEnvelope(
            channel=self.channel_name,
            conversation_id=kwargs.get("conversation_id") or "",
            user_id=kwargs.get("user_id") or metadata.get("web_user_id", ""),
            sender=kwargs.get("sender") or "web_user",
            attachments=list(kwargs.get("attachments") or []),
            metadata=metadata,
        )

    def parse_event(self, raw_event: dict[str, Any]) -> dict[str, Any] | None:
        """解析 Web 前端消息事件格式

        Web 前端发送的消息通常为：
        {
            "content": "hello",
            "conversation_id": "xxx",
            "user_id": "web_user_123",
            "sender": "用户昵称",
            "message_id": "msg_xxx",
            "attachments": [...]
        }
        """
        content = raw_event.get("content", "")
        if not content and not raw_event.get("attachments"):
            return None

        content = self.normalize_inbound_message(content)
        conversation_id = (
            raw_event.get("conversation_id")
            or f"web:{raw_event.get('user_id', '')}"
        )
        user_id = str(raw_event.get("user_id", ""))
        sender = raw_event.get("sender") or (f"Web用户{user_id[-4:]}" if user_id else "web_user")

        return {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "sender": sender,
            "content": content,
            "message_id": raw_event.get("message_id", ""),
            "attachments": list(raw_event.get("attachments") or []),
            "metadata": {
                "web_session_id": raw_event.get("session_id", ""),
                "web_user_agent": raw_event.get("user_agent", ""),
            },
        }
