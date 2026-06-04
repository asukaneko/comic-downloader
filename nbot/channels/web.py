from typing import Any

from nbot.channels.base import BaseChannelAdapter, ChannelCapabilities, ChannelEnvelope
from nbot.character.channel_context import ChannelRenderPolicy, ChannelRuntimeContext


class WebChannelAdapter(BaseChannelAdapter):
    """Web 前端频道适配器

    同时实现 CharacterChannelAdapter 协议，接入角色运行时。
    """

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

    # ------------------------------------------------------------------
    # CharacterChannelAdapter 协议方法
    # ------------------------------------------------------------------

    def build_runtime_context(self, chat_request: Any) -> ChannelRuntimeContext:
        """从 ChatRequest 构建 Web 频道运行上下文"""
        meta = getattr(chat_request, "metadata", {}) or {}
        return ChannelRuntimeContext(
            channel=self.channel_name,
            conversation_id=getattr(chat_request, "conversation_id", "") or "",
            scene="web_session",
            user_id=getattr(chat_request, "user_id", "") or "",
            user_display_name=getattr(chat_request, "sender", "") or "",
            metadata=meta,
        )

    def get_render_policy(self, context: ChannelRuntimeContext) -> ChannelRenderPolicy:
        """Web 频道渲染策略"""
        return ChannelRenderPolicy(
            supports_stream=True,
            supports_markdown=True,
            supports_image=True,
            supports_file=True,
            supports_quote_reply=False,
            supports_at=False,
            max_text_length=None,
            split_strategy="none",
        )

    def select_character_id(self, context: ChannelRuntimeContext) -> str | None:
        """Web 频道角色选择（使用默认，由 nekobot adapter 的复杂 fallback 决定）"""
        return None

    def resolve_memory_scope(self, context: ChannelRuntimeContext) -> str:
        """Web 频道默认记忆作用域：按会话隔离"""
        return "conversation"

    def render_result(self, result: Any, context: ChannelRuntimeContext) -> list[dict[str, Any]]:
        """Web 不需要渲染，结果由 Pipeline 直接返回"""
        return []
