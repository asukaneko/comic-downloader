from typing import Any

from nbot.channels.base import BaseChannelAdapter, ChannelCapabilities, ChannelEnvelope
from nbot.character.channel_context import ChannelRenderPolicy, ChannelRuntimeContext


class QQBotChannelAdapter(BaseChannelAdapter):
    """QQ Bot official channel adapter for Lobster/agent QQ Bot events."""

    channel_name = "qqbot"

    def __init__(self, bot_appid: str = ""):
        self.bot_appid = str(bot_appid or "").strip()

    def get_capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            supports_stream=False,
            supports_progress_updates=False,
            supports_file_send=False,
            supports_stop=False,
        )

    def build_envelope(self, **kwargs) -> ChannelEnvelope:
        metadata = dict(kwargs.get("metadata") or {})
        conversation_id = kwargs.get("conversation_id") or self._conversation_id_from_meta(metadata)
        return ChannelEnvelope(
            channel=self.channel_name,
            conversation_id=conversation_id,
            user_id=kwargs.get("user_id") or "",
            sender=kwargs.get("sender") or "qqbot_user",
            attachments=list(kwargs.get("attachments") or []),
            metadata=metadata,
        )

    def parse_event(self, raw_event: dict[str, Any]) -> dict[str, Any] | None:
        event_type = str(raw_event.get("t") or raw_event.get("event_type") or "").strip()
        data = raw_event.get("d") or raw_event.get("event") or raw_event
        if not isinstance(data, dict):
            return None

        if event_type in ("C2C_MESSAGE_CREATE", "DIRECT_MESSAGE_CREATE"):
            return self._parse_private_message(event_type, data, raw_event)
        if event_type in ("GROUP_AT_MESSAGE_CREATE", "GROUP_MESSAGE_CREATE", "AT_MESSAGE_CREATE"):
            return self._parse_group_message(event_type, data, raw_event)
        return None

    def _parse_private_message(
        self,
        event_type: str,
        data: dict[str, Any],
        raw_event: dict[str, Any],
    ) -> dict[str, Any] | None:
        author = data.get("author") or data.get("sender") or {}
        user_id = str(
            data.get("user_openid")
            or data.get("openid")
            or author.get("user_openid")
            or author.get("openid")
            or author.get("id")
            or ""
        ).strip()
        content = self.normalize_inbound_message(str(data.get("content") or ""))
        attachments = self._extract_attachments(data)
        if not user_id or (not content and not attachments):
            return None

        message_id = str(data.get("id") or data.get("msg_id") or "").strip()
        return {
            "conversation_id": f"qqbot:private:{user_id}",
            "user_id": user_id,
            "sender": str(author.get("username") or author.get("nick") or "qqbot_user"),
            "content": content,
            "message_id": message_id,
            "attachments": attachments,
            "metadata": {
                "qqbot_event_type": event_type,
                "qqbot_scene": "private",
                "qqbot_user_openid": user_id,
                "qqbot_message_id": message_id,
                "qqbot_event_id": raw_event.get("id") or raw_event.get("s"),
            },
        }

    def _parse_group_message(
        self,
        event_type: str,
        data: dict[str, Any],
        raw_event: dict[str, Any],
    ) -> dict[str, Any] | None:
        author = data.get("author") or data.get("member") or {}
        group_id = str(
            data.get("group_openid")
            or data.get("group_id")
            or data.get("guild_id")
            or data.get("channel_id")
            or ""
        ).strip()
        user_id = str(
            data.get("member_openid")
            or author.get("member_openid")
            or author.get("user_openid")
            or author.get("openid")
            or author.get("id")
            or ""
        ).strip()
        content = self.normalize_inbound_message(str(data.get("content") or ""))
        attachments = self._extract_attachments(data)
        if not group_id or (not content and not attachments):
            return None

        message_id = str(data.get("id") or data.get("msg_id") or "").strip()
        is_mentioned = event_type in ("GROUP_AT_MESSAGE_CREATE", "AT_MESSAGE_CREATE")
        if not is_mentioned:
            is_mentioned = self._is_bot_mentioned(data, content)
        if event_type == "GROUP_MESSAGE_CREATE" and not is_mentioned:
            return None

        return {
            "conversation_id": f"qqbot:group:{group_id}",
            "user_id": user_id,
            "sender": str(author.get("username") or author.get("nick") or "qqbot_user"),
            "content": content,
            "message_id": message_id,
            "attachments": attachments,
            "metadata": {
                "qqbot_event_type": event_type,
                "qqbot_scene": "group",
                "qqbot_group_openid": group_id,
                "qqbot_user_openid": user_id,
                "qqbot_message_id": message_id,
                "qqbot_event_id": raw_event.get("id") or raw_event.get("s"),
                "is_mentioned": is_mentioned,
            },
        }

    def _is_bot_mentioned(self, data: dict[str, Any], content: str) -> bool:
        mentions = data.get("mentions") or data.get("mention_users") or []
        if isinstance(mentions, list):
            for item in mentions:
                if not isinstance(item, dict):
                    continue
                mention_id = str(
                    item.get("id")
                    or item.get("user_openid")
                    or item.get("openid")
                    or item.get("bot_appid")
                    or ""
                ).strip()
                if self.bot_appid and mention_id == self.bot_appid:
                    return True
                if item.get("bot") is True or item.get("is_bot") is True:
                    return True
        if self.bot_appid and self.bot_appid in (content or ""):
            return True
        return False

    @staticmethod
    def _extract_attachments(data: dict[str, Any]) -> list[dict[str, Any]]:
        attachments: list[dict[str, Any]] = []
        raw_attachments = data.get("attachments") or []
        if not isinstance(raw_attachments, list):
            return attachments
        for item in raw_attachments:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or item.get("source_ref") or "").strip()
            content_type = str(item.get("content_type") or item.get("mime_type") or "")
            att_type = "image" if content_type.startswith("image/") else "file"
            attachments.append(
                {
                    "type": att_type,
                    "source": "qqbot",
                    "source_ref": url,
                    "url": url,
                    "mime_type": content_type,
                    "name": item.get("filename") or item.get("name") or "",
                }
            )
        return attachments

    @staticmethod
    def _conversation_id_from_meta(metadata: dict[str, Any]) -> str:
        scene = str(metadata.get("qqbot_scene") or "").strip()
        if scene == "group":
            group_id = metadata.get("qqbot_group_openid") or metadata.get("group_openid")
            return f"qqbot:group:{group_id}" if group_id else ""
        user_id = metadata.get("qqbot_user_openid") or metadata.get("user_openid")
        return f"qqbot:private:{user_id}" if user_id else ""

    def build_runtime_context(self, chat_request: Any) -> ChannelRuntimeContext:
        meta = getattr(chat_request, "metadata", {}) or {}
        scene = str(meta.get("qqbot_scene") or "").strip()
        if not scene:
            conversation_id = getattr(chat_request, "conversation_id", "") or ""
            scene = "group" if conversation_id.startswith("qqbot:group:") else "private"

        return ChannelRuntimeContext(
            channel=self.channel_name,
            conversation_id=getattr(chat_request, "conversation_id", "") or "",
            scene=scene,
            user_id=getattr(chat_request, "user_id", "") or "",
            user_display_name=getattr(chat_request, "sender", "") or "",
            group_id=meta.get("qqbot_group_openid", "") if scene == "group" else "",
            metadata=meta,
        )

    def get_render_policy(self, context: ChannelRuntimeContext) -> ChannelRenderPolicy:
        return ChannelRenderPolicy(
            supports_stream=False,
            supports_markdown=False,
            supports_image=True,
            supports_file=False,
            supports_quote_reply=True,
            supports_at=True,
            max_text_length=2000,
            split_strategy="paragraph",
        )

    def select_character_id(self, context: ChannelRuntimeContext) -> str | None:
        return None

    def resolve_memory_scope(self, context: ChannelRuntimeContext) -> str:
        if context.scene == "private":
            return "user"
        return "group"

    def render_result(self, result: Any, context: ChannelRuntimeContext) -> list[dict[str, Any]]:
        text = getattr(result, "text", "") or ""
        if not text:
            return []
        return [{"type": "text", "content": text}]
