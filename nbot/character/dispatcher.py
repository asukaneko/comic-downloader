"""
角色运行时上下文调度器

协调频道适配器和角色运行时，提供统一的角色上下文准备入口。

注意：本模块负责角色上下文准备（before_turn），不负责 AI 调用。
AI 调用由上层 Pipeline 完成，after_turn 在 Pipeline 结束后调用。
"""

from __future__ import annotations

import logging
from typing import Any

from nbot.character.channel_adapter import CharacterChannelAdapter
from nbot.character.channel_context import ChannelRuntimeContext
from nbot.character.runtime import CharacterRuntime
from nbot.character.runtime_request import CharacterRuntimeRequest, CharacterRuntimeResult

logger = logging.getLogger(__name__)


def build_scope_id(context: ChannelRuntimeContext, memory_scope: str) -> str:
    """根据记忆作用域配置构建 scope_id

    Args:
        context: 频道运行上下文
        memory_scope: 记忆作用域配置

    Returns:
        scope_id 字符串
    """
    channel = context.channel or "unknown"
    user_id = context.user_id or "anonymous"
    group_id = context.group_id or ""
    conversation_id = context.conversation_id or "unknown_conversation"
    thread_id = context.thread_id or ""

    # 空值兜底
    if memory_scope in ("group", "group_user") and not group_id:
        logger.warning(
            "%s scope requested but group_id is empty, falling back to conversation_id",
            memory_scope,
        )
        group_id = conversation_id
    if memory_scope == "thread" and not thread_id:
        logger.warning(
            "thread scope requested but thread_id is empty, falling back to conversation_id",
        )
        thread_id = conversation_id

    if memory_scope == "conversation":
        return f"{channel}:conversation:{conversation_id}"
    if memory_scope == "user":
        return f"{channel}:user:{user_id}"
    if memory_scope == "group":
        return f"{channel}:group:{group_id}"
    if memory_scope == "group_user":
        return f"{channel}:group:{group_id}:user:{user_id}"
    if memory_scope == "chat_user":
        return f"{channel}:chat:{conversation_id}:user:{user_id}"
    if memory_scope == "thread":
        return f"{channel}:chat:{conversation_id}:thread:{thread_id}"
    # 默认按会话隔离
    return f"{channel}:conversation:{conversation_id}"


class CharacterRuntimeContextDispatcher:
    """角色运行时上下文调度器

    职责：
    1. 根据频道找到对应的适配器
    2. 构造统一角色运行上下文
    3. 判断该频道是否启用角色进行时
    4. 选择角色卡和记忆作用域（配置优先于 adapter 默认值）
    5. 调用角色运行时的 before_turn
    6. 返回角色上下文供 Pipeline 使用

    注意：本调度器只负责上下文准备，不负责 AI 调用和 after_turn。
    """

    def __init__(
        self,
        runtime: CharacterRuntime,
        config: dict[str, Any] | None = None,
    ):
        self._runtime = runtime
        self._config = config or {}
        self._adapters: dict[str, CharacterChannelAdapter] = {}

    def register_adapter(self, adapter: CharacterChannelAdapter) -> None:
        """注册频道适配器"""
        self._adapters[adapter.channel_name] = adapter
        logger.info("Registered character channel adapter: %s", adapter.channel_name)

    def get_adapter(self, channel: str) -> CharacterChannelAdapter | None:
        """获取频道适配器"""
        return self._adapters.get(channel)

    def _get_channel_config(self, channel: str) -> dict[str, Any]:
        """获取频道配置"""
        return self._config.get("channels", {}).get(channel, {})

    def _get_global_config(self) -> dict[str, Any]:
        """获取全局角色运行时配置"""
        return self._config.get("character_runtime", {})

    def is_enabled(self, context: ChannelRuntimeContext) -> bool:
        """检查频道是否启用角色运行时

        逻辑：频道显式配置优先，否则使用全局默认。
        - enabled=false 可以显式关闭
        - enabled=true 可以显式开启（即使全局关闭）
        """
        runtime_config = self._get_channel_config(context.channel).get("character_runtime", {})
        global_enabled = self._get_global_config().get("default_enabled", True)

        # 频道显式配置时，以频道配置为准
        if "enabled" in runtime_config:
            return bool(runtime_config["enabled"])

        # 频道未配置时，使用全局默认
        return bool(global_enabled)

    def get_trigger_strategy(self, context: ChannelRuntimeContext) -> str:
        """获取触发策略"""
        return self._get_channel_config(context.channel).get(
            "character_runtime", {}
        ).get("trigger", "always")

    def get_memory_scope(self, context: ChannelRuntimeContext) -> str:
        """获取记忆作用域（从配置读取）"""
        return self._get_channel_config(context.channel).get(
            "character_runtime", {}
        ).get("memory_scope", "conversation")

    def get_default_character_id(self, context: ChannelRuntimeContext) -> str:
        """获取默认角色卡 ID"""
        runtime_config = self._get_channel_config(context.channel).get("character_runtime", {})

        # 优先使用频道级别配置
        channel_character = runtime_config.get("default_character_id", "")
        if channel_character:
            return channel_character

        # 回退到全局配置
        return self._get_global_config().get("default_character_id", "")

    def get_legacy_prompt_enabled(self, context: ChannelRuntimeContext) -> bool:
        """检查是否启用旧版 prompt"""
        return self._get_channel_config(context.channel).get(
            "character_runtime", {}
        ).get("legacy_prompt_enabled", False)

    def resolve_memory_scope(
        self,
        context: ChannelRuntimeContext,
        adapter: CharacterChannelAdapter,
    ) -> str:
        """确定记忆作用域（配置优先于 adapter 默认值）

        Args:
            context: 频道运行上下文
            adapter: 频道适配器

        Returns:
            记忆作用域
        """
        runtime_config = self._get_channel_config(context.channel).get("character_runtime", {})

        # 只要配置文件显式提供 memory_scope，就以配置为准；conversation 也是有效配置值。
        if "memory_scope" in runtime_config:
            configured_scope = str(runtime_config.get("memory_scope") or "").strip()
            result = configured_scope or "conversation"
            # 私聊场景下 group/group_user scope 无意义，降级为 user
            if result in ("group", "group_user") and context.scene == "private":
                return "user"
            return result

        # adapter 兜底
        adapter_scope = adapter.resolve_memory_scope(context)
        return adapter_scope or "conversation"

    async def prepare_context(
        self,
        chat_request: Any,
        channel: str,
    ) -> CharacterRuntimeResult | None:
        """准备角色运行上下文（before_turn）

        Args:
            chat_request: 原始聊天请求
            channel: 频道标识

        Returns:
            角色运行结果（包含 prompt_text），未启用或出错时返回 None
        """
        # 1. 获取频道适配器
        adapter = self.get_adapter(channel)
        if adapter is None:
            logger.debug("No character adapter for channel: %s", channel)
            return None

        # 2. 构建频道运行上下文
        context = adapter.build_runtime_context(chat_request)

        # 3. 检查是否启用角色运行时
        if not self.is_enabled(context):
            logger.debug("Character runtime not enabled for channel: %s", channel)
            return None

        # 4. 获取触发策略并检查是否应该触发
        trigger = self.get_trigger_strategy(context)
        if not self._should_trigger(trigger, context, chat_request):
            logger.debug("Trigger strategy %s not met for message", trigger)
            return None

        # 5. 选择角色卡
        character_id = adapter.select_character_id(context)
        if character_id is None:
            character_id = self.get_default_character_id(context)

        # 6. 确定记忆作用域（配置优先于 adapter）
        memory_scope = self.resolve_memory_scope(context, adapter)

        # 7. 构建 scope_id
        scope_id = build_scope_id(context, memory_scope)

        # 8. 获取渲染策略
        render_policy = adapter.get_render_policy(context)

        # 9. 构建角色运行请求
        request = CharacterRuntimeRequest(
            context=context,
            content=getattr(chat_request, "content", ""),
            sender=(
                getattr(chat_request, "sender", "")
                or context.user_display_name
                or ""
            ),
            user_id=getattr(chat_request, "user_id", "") or context.user_id,
            attachments=getattr(chat_request, "attachments", []),
            character_id=character_id or None,
            parent_message_id=getattr(chat_request, "parent_message_id", None),
            metadata={
                "memory_scope": memory_scope,
                "scope_id": scope_id,
                "render_policy": render_policy.to_dict(),
            },
        )

        # 10. 调用角色运行时
        try:
            result = await self._run_before_turn(request)
            return result
        except Exception:
            logger.exception("Character runtime error for channel: %s", channel)
            return None

    async def _run_before_turn(
        self,
        request: CharacterRuntimeRequest,
    ) -> CharacterRuntimeResult:
        """执行角色运行时 before_turn"""
        from nbot.character.models import CharacterIdentity

        # 使用正确的 scope_id
        scope_id = request.metadata.get("scope_id", request.context.conversation_id)

        # 构建 CharacterIdentity
        identity = CharacterIdentity(
            character_id=request.character_id or "",
            target_id=request.user_id,
            scope_id=scope_id,
            channel=request.context.channel,
        )

        # 构建 chat_request 兼容对象
        class ChatRequestCompat:
            def __init__(self, req: CharacterRuntimeRequest):
                self.content = req.content
                self.sender = req.sender
                self.user_id = req.user_id
                self.attachments = req.attachments
                self.metadata = req.metadata

        compat_request = ChatRequestCompat(request)

        # 调用 before_turn
        turn_context = self._runtime.before_turn(
            chat_request=compat_request,
            identity=identity,
            recent_messages=request.metadata.get("recent_messages", []),
        )

        # 构建结果（identity 序列化为 dict，避免序列化问题）
        return CharacterRuntimeResult(
            text="",  # AI 回复由 Pipeline 填充
            assistant_message={},
            state_patch={
                "turn_context": turn_context,
                "profile": turn_context.profile.to_dict() if turn_context.profile else None,
                "state": turn_context.state.to_dict() if turn_context.state else None,
                "relationship": turn_context.relationship.to_dict() if turn_context.relationship else None,
            },
            metadata={
                "prompt_text": turn_context.prompt_text,
                "character_id": request.character_id,
                "memory_scope": request.metadata.get("memory_scope"),
                "scope_id": scope_id,
                "identity_character_id": identity.character_id,
                "identity_target_id": identity.target_id,
                "identity_scope_id": identity.scope_id,
                "identity_channel": identity.channel,
            },
        )

    @staticmethod
    def _get_meta_field(chat_request: Any, key: str, default: Any = None) -> Any:
        """从 chat_request 属性或 metadata 字典中获取字段

        Adapter 通常将 is_mentioned / is_reply_to_bot 写入 metadata 字典，
        但也可能直接设置为 chat_request 属性。此方法同时检查两处。
        """
        direct = getattr(chat_request, key, None)
        if direct is not None:
            return direct
        meta = getattr(chat_request, "metadata", None) or {}
        return meta.get(key, default)

    def _should_trigger(
        self,
        trigger: str,
        context: ChannelRuntimeContext,
        chat_request: Any,
    ) -> bool:
        """检查是否应该触发角色运行时"""
        if trigger == "always":
            return True

        if trigger == "private_only":
            return context.scene == "private"

        if trigger == "mention_only":
            return bool(self._get_meta_field(chat_request, "is_mentioned", False))

        if trigger == "mention_or_private":
            if context.scene == "private":
                return True
            return bool(self._get_meta_field(chat_request, "is_mentioned", False))

        if trigger == "private_or_reply":
            # Telegram 常用策略：私聊总是触发，回复时触发
            if context.scene == "private":
                return True
            return bool(self._get_meta_field(chat_request, "is_reply_to_bot", False))

        if trigger == "keyword":
            keywords = self._get_channel_config(context.channel).get(
                "character_runtime", {}
            ).get("trigger_keywords", [])
            content = getattr(chat_request, "content", "")
            return any(kw in content for kw in keywords)

        if trigger == "manual":
            return getattr(chat_request, "character_mode", False)

        return False


# 向后兼容
CharacterRuntimeDispatcher = CharacterRuntimeContextDispatcher