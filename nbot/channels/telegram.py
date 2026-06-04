from typing import Any

from nbot.channels.base import BaseChannelAdapter, ChannelCapabilities, ChannelEnvelope
from nbot.character.channel_context import ChannelRenderPolicy, ChannelRuntimeContext


class TelegramChannelAdapter(BaseChannelAdapter):
    """Telegram 频道适配器

    同时实现 CharacterChannelAdapter 协议，接入角色运行时。
    """

    channel_name = "telegram"

    def get_capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            supports_stream=False,
            supports_progress_updates=False,
            supports_file_send=True,
            supports_stop=False,
        )

    def build_envelope(self, **kwargs) -> ChannelEnvelope:
        metadata = dict(kwargs.get("metadata") or {})
        chat_id = metadata.get("telegram_chat_id") or metadata.get("chat_id")
        conversation_id = kwargs.get("conversation_id") or (
            f"telegram:{chat_id}" if chat_id else ""
        )
        return ChannelEnvelope(
            channel=self.channel_name,
            conversation_id=conversation_id,
            user_id=kwargs.get("user_id") or "",
            sender=kwargs.get("sender") or "telegram_user",
            attachments=list(kwargs.get("attachments") or []),
            metadata=metadata,
        )

    def parse_event(self, raw_event: dict[str, Any]) -> dict[str, Any] | None:
        """解析 Telegram Update 事件格式（兼容 parse_update 别名）"""
        return self.parse_update(raw_event)

    def parse_update(self, update: dict[str, Any]) -> dict[str, Any] | None:
        """解析 Telegram Bot API Update 对象"""
        message = update.get("message") or update.get("edited_message")
        if not isinstance(message, dict):
            return None

        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            return None

        text = message.get("text") or message.get("caption") or ""
        text = self.normalize_inbound_message(text)
        if not text:
            return None

        username = sender.get("username") or sender.get("first_name") or "telegram_user"
        user_id = sender.get("id")

        # 检测是否回复机器人消息
        reply_to = message.get("reply_to_message") or {}
        reply_from = reply_to.get("from") or {}
        is_reply_to_bot = bool(reply_from.get("is_bot", False))

        return {
            "conversation_id": f"telegram:{chat_id}",
            "user_id": str(user_id) if user_id is not None else "",
            "sender": username,
            "content": text,
            "message_id": message.get("message_id"),
            "attachments": [],
            "is_reply_to_bot": is_reply_to_bot,
            "metadata": {
                "telegram_update_id": update.get("update_id"),
                "telegram_chat_id": str(chat_id),
                "telegram_message_id": message.get("message_id"),
                "telegram_chat_type": chat.get("type"),
                "is_reply_to_bot": is_reply_to_bot,
            },
        }

    # ------------------------------------------------------------------
    # CharacterChannelAdapter 协议方法
    # ------------------------------------------------------------------

    def build_runtime_context(self, chat_request: Any) -> ChannelRuntimeContext:
        """从 ChatRequest 构建 Telegram 频道运行上下文"""
        meta = getattr(chat_request, "metadata", {}) or {}
        chat_type = meta.get("telegram_chat_type", "")
        scene = "private" if chat_type == "private" else "group"

        return ChannelRuntimeContext(
            channel=self.channel_name,
            conversation_id=getattr(chat_request, "conversation_id", "") or "",
            scene=scene,
            user_id=getattr(chat_request, "user_id", "") or "",
            user_display_name=getattr(chat_request, "sender", "") or "",
            group_id="" if scene == "private" else meta.get("telegram_chat_id", ""),
            metadata=meta,
        )

    def get_render_policy(self, context: ChannelRuntimeContext) -> ChannelRenderPolicy:
        """Telegram 频道渲染策略"""
        return ChannelRenderPolicy(
            supports_stream=False,
            supports_markdown=True,
            supports_image=True,
            supports_file=True,
            supports_quote_reply=True,
            supports_at=False,
            max_text_length=4096,
            split_strategy="paragraph",
        )

    def select_character_id(self, context: ChannelRuntimeContext) -> str | None:
        """Telegram 频道角色选择（使用默认）"""
        return None

    def resolve_memory_scope(self, context: ChannelRuntimeContext) -> str:
        """Telegram 频道默认记忆作用域"""
        if context.scene == "private":
            return "user"
        return "group"

    def render_result(self, result: Any, context: ChannelRuntimeContext) -> list[dict[str, Any]]:
        """将角色运行结果渲染为 Telegram 消息格式"""
        text = getattr(result, "text", "") or ""
        if not text:
            return []
        return [{"type": "text", "content": text}]
