from typing import Any

from nbot.channels.base import BaseChannelAdapter, ChannelCapabilities, ChannelEnvelope
from nbot.character.channel_context import ChannelRenderPolicy, ChannelRuntimeContext


class QQChannelAdapter(BaseChannelAdapter):
    """QQ 频道适配器（OneBot v11 协议）

    同时实现 CharacterChannelAdapter 协议，接入角色运行时。
    """

    channel_name = "qq"

    def get_capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            supports_stream=False,
            supports_progress_updates=False,
            supports_file_send=True,
            supports_stop=False,
        )

    def build_envelope(self, **kwargs) -> ChannelEnvelope:
        metadata = dict(kwargs.get("metadata") or {})
        group_id = metadata.get("group_id")
        user_id = kwargs.get("user_id") or metadata.get("user_id") or ""

        # 优先使用传入的 conversation_id，支持外部配置会话隔离模式
        conversation_id = kwargs.get("conversation_id")
        if not conversation_id:
            if group_id:
                # 支持两种群聊会话模式：
                # - group:      群共享上下文（默认）
                # - group_user: 群内用户隔离上下文
                group_mode = metadata.get("group_session_mode", "group")
                if group_mode == "group_user" and user_id:
                    conversation_id = f"qq:group:{group_id}:{user_id}"
                else:
                    conversation_id = f"qq:group:{group_id}"
            else:
                conversation_id = f"qq:private:{user_id}"

        return ChannelEnvelope(
            channel=self.channel_name,
            conversation_id=conversation_id,
            user_id=user_id,
            sender=kwargs.get("sender") or "qq_user",
            attachments=list(kwargs.get("attachments") or []),
            metadata=metadata,
        )

    def parse_event(self, raw_event: dict[str, Any]) -> dict[str, Any] | None:
        """解析 OneBot v11 事件格式

        支持的事件类型：
        - message（群消息/私消息）
        - post_type=message, message_type=group/private

        OneBot v11 事件示例：
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "message_id": 12345,
            "user_id": 67890,
            "group_id": 11111,
            "raw_message": "hello",
            "message": [{"type": "text", "data": {"text": "hello"}}],
            "sender": {"user_id": 67890, "nickname": "xxx", "role": "member"}
        }
        """
        post_type = raw_event.get("post_type", "")

        # 只处理消息事件
        if post_type != "message":
            return None

        message_type = raw_event.get("message_type", "")
        if message_type not in ("group", "private"):
            return None

        # 提取消息内容
        raw_message = raw_event.get("raw_message", "")
        message_segments = raw_event.get("message", [])

        # 从 CQ 码段提取纯文本
        text_parts = []
        attachments = []
        for seg in (message_segments if isinstance(message_segments, list) else []):
            if isinstance(seg, dict):
                seg_type = seg.get("type", "")
                seg_data = seg.get("data", {})
                if seg_type == "text":
                    text_parts.append(seg_data.get("text", ""))
                elif seg_type == "image":
                    attachments.append({
                        "type": "image",
                        "source": "qq",
                        "file": seg_data.get("file", ""),
                        "url": seg_data.get("url", ""),
                    })
                elif seg_type == "at":
                    text_parts.append(f"@{seg_data.get('qq', '')}")
                elif seg_type == "reply":
                    attachments.append({
                        "type": "reply",
                        "source": "qq",
                        "id": seg_data.get("id", ""),
                    })
                elif seg_type == "face":
                    text_parts.append("[表情]")

        # 检测是否被 @
        bot_uin = str(getattr(self, "bot_uin", "") or "")
        is_mentioned = False
        if message_type == "group":
            for seg in (message_segments if isinstance(message_segments, list) else []):
                if isinstance(seg, dict) and seg.get("type") == "at":
                    at_qq = str(seg.get("data", {}).get("qq", ""))
                    if at_qq == bot_uin or at_qq == "all":
                        is_mentioned = True
                        break

        # 如果 CQ 码解析无文本，使用 raw_message 兜底
        content = "".join(text_parts).strip() or raw_message

        # 提取发送者信息
        sender = raw_event.get("sender") or {}
        user_id = str(raw_event.get("user_id", "") or sender.get("user_id", ""))
        nickname = sender.get("nickname", "")
        sender_name = nickname or f"QQ用户{user_id}" if user_id else "qq_user"

        # 提取会话信息
        group_id = raw_event.get("group_id")
        if message_type == "group" and group_id:
            conversation_id = f"qq:group:{group_id}"
        else:
            conversation_id = f"qq:private:{user_id}"

        message_id = str(raw_event.get("message_id", ""))

        content = self.normalize_inbound_message(content)
        if not content and not attachments:
            return None

        return {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "sender": sender_name,
            "content": content,
            "message_id": message_id,
            "attachments": attachments,
            "is_mentioned": is_mentioned,
            "metadata": {
                "post_type": post_type,
                "message_type": message_type,
                "sub_type": raw_event.get("sub_type", ""),
                "group_id": str(group_id) if group_id else "",
                "sender_nickname": nickname,
                "sender_role": sender.get("role", ""),
                "raw_message": raw_message,
                "is_mentioned": is_mentioned,
            },
        }

    # ------------------------------------------------------------------
    # CharacterChannelAdapter 协议方法
    # ------------------------------------------------------------------

    def build_runtime_context(self, chat_request: Any) -> ChannelRuntimeContext:
        """从 ChatRequest 构建 QQ 频道运行上下文"""
        meta = getattr(chat_request, "metadata", {}) or {}
        group_id = meta.get("group_id", "")
        user_id = getattr(chat_request, "user_id", "") or ""
        scene = "group" if group_id else "private"

        return ChannelRuntimeContext(
            channel=self.channel_name,
            conversation_id=getattr(chat_request, "conversation_id", "") or "",
            scene=scene,
            user_id=user_id,
            user_display_name=getattr(chat_request, "sender", "") or "",
            group_id=group_id,
            metadata=meta,
        )

    def get_render_policy(self, context: ChannelRuntimeContext) -> ChannelRenderPolicy:
        """QQ 频道渲染策略"""
        return ChannelRenderPolicy(
            supports_stream=False,
            supports_markdown=False,
            supports_image=True,
            supports_file=True,
            supports_quote_reply=True,
            supports_at=True,
            max_text_length=4500,
            split_strategy="paragraph",
        )

    def select_character_id(self, context: ChannelRuntimeContext) -> str | None:
        """QQ 频道角色选择（使用默认）"""
        return None

    def resolve_memory_scope(self, context: ChannelRuntimeContext) -> str:
        """QQ 频道默认记忆作用域"""
        if context.scene == "group":
            return "group"
        return "user"

    def render_result(self, result: Any, context: ChannelRuntimeContext) -> list[dict[str, Any]]:
        """将角色运行结果渲染为 QQ 消息格式"""
        text = getattr(result, "text", "") or ""
        if not text:
            metadata = getattr(result, "metadata", {}) or {}
            text = metadata.get("prompt_text", "")
        if not text:
            return []
        return [{"type": "text", "content": text}]
