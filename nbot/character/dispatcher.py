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
    channel = context.channel
    user_id = context.user_id
    group_id = context.group_id
    conversation_id = context.conversation_id
    thread_id = context.thread_id

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
    4. 选择角色卡和记忆作用域
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
        """注册频道适配器

        Args:
            adapter: 实现了 CharacterChannelAdapter 协议的适配器
        """
        self._adapters[adapter.channel_name] = adapter
        logger.info("Registered character channel adapter: %s", adapter.channel_name)

    def get_adapter(self, channel: str) -> CharacterChannelAdapter | None:
        """获取频道适配器

        Args:
            channel: 频道标识

        Returns:
            适配器实例，未注册则返回 None
        """
        return self._adapters.get(channel)

    def _get_channel_config(self, channel: str) -> dict[str, Any]:
        """获取频道配置

        Args:
            channel: 频道标识

        Returns:
            频道配置字典
        """
        channels = self._config.get("channels", {})
        return channels.get(channel, {})

    def _get_global_config(self) -> dict[str, Any]:
        """获取全局角色运行时配置

        Returns:
            全局配置字典
        """
        return self._config.get("character_runtime", {})

    def is_enabled(self, context: ChannelRuntimeContext) -> bool:
        """检查频道是否启用角色运行时

        Args:
            context: 频道运行上下文

        Returns:
            是否启用
        """
        channel_config = self._get_channel_config(context.channel)
        runtime_config = channel_config.get("character_runtime", {})

        # 检查频道级别开关
        channel_enabled = runtime_config.get("enabled", False)

        # 检查全局默认开关
        global_config = self._get_global_config()
        global_enabled = global_config.get("default_enabled", True)

        # 频道显式开启时，忽略全局设置
        if channel_enabled:
            return True

        # 全局关闭时，需要频道显式开启
        if not global_enabled:
            return False

        # 全局开启但频道未配置时，默认启用
        return True

    def get_trigger_strategy(self, context: ChannelRuntimeContext) -> str:
        """获取触发策略

        Args:
            context: 频道运行上下文

        Returns:
            触发策略: always, private_only, mention_only, mention_or_private,
                     private_or_reply, keyword, manual
        """
        channel_config = self._get_channel_config(context.channel)
        runtime_config = channel_config.get("character_runtime", {})
        return runtime_config.get("trigger", "always")

    def get_memory_scope(self, context: ChannelRuntimeContext) -> str:
        """获取记忆作用域

        Args:
            context: 频道运行上下文

        Returns:
            作用域: conversation, user, group, group_user, chat_user, thread
        """
        channel_config = self._get_channel_config(context.channel)
        runtime_config = channel_config.get("character_runtime", {})
        return runtime_config.get("memory_scope", "conversation")

    def get_default_character_id(self, context: ChannelRuntimeContext) -> str:
        """获取默认角色卡 ID

        Args:
            context: 频道运行上下文

        Returns:
            角色卡 ID
        """
        channel_config = self._get_channel_config(context.channel)
        runtime_config = channel_config.get("character_runtime", {})

        # 优先使用频道级别配置
        channel_character = runtime_config.get("default_character_id", "")
        if channel_character:
            return channel_character

        # 回退到全局配置
        global_config = self._get_global_config()
        return global_config.get("default_character_id", "")

    def get_legacy_prompt_enabled(self, context: ChannelRuntimeContext) -> bool:
        """检查是否启用旧版 prompt

        Args:
            context: 频道运行上下文

        Returns:
            是否启用旧版 prompt
        """
        channel_config = self._get_channel_config(context.channel)
        runtime_config = channel_config.get("character_runtime", {})
        return runtime_config.get("legacy_prompt_enabled", False)

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

        # 6. 确定记忆作用域
        memory_scope = adapter.resolve_memory_scope(context)

        # 7. 构建 scope_id
        scope_id = build_scope_id(context, memory_scope)

        # 8. 获取渲染策略
        render_policy = adapter.get_render_policy(context)

        # 9. 构建角色运行请求
        request = CharacterRuntimeRequest(
            context=context,
            content=getattr(chat_request, "content", ""),
            sender=getattr(chat_request, "sender", ""),
            user_id=getattr(chat_request, "user_id", ""),
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
        """执行角色运行时 before_turn

        Args:
            request: 角色运行请求

        Returns:
            角色运行结果
        """
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

        # 构建结果
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
                "identity": identity,
            },
        )

    def _should_trigger(
        self,
        trigger: str,
        context: ChannelRuntimeContext,
        chat_request: Any,
    ) -> bool:
        """检查是否应该触发角色运行时

        Args:
            trigger: 触发策略
            context: 频道运行上下文
            chat_request: 原始聊天请求

        Returns:
            是否应该触发
        """
        if trigger == "always":
            return True

        if trigger == "private_only":
            return context.scene == "private"

        if trigger == "mention_only":
            return getattr(chat_request, "is_mentioned", False)

        if trigger == "mention_or_private":
            if context.scene == "private":
                return True
            return getattr(chat_request, "is_mentioned", False)

        if trigger == "private_or_reply":
            # Telegram 常用策略：私聊总是触发，回复时触发
            if context.scene == "private":
                return True
            return getattr(chat_request, "is_reply_to_bot", False)

        if trigger == "keyword":
            keywords = self._get_channel_config(context.channel).get(
                "character_runtime", {}
            ).get("trigger_keywords", [])
            content = getattr(chat_request, "content", "")
            return any(kw in content for kw in keywords)

        if trigger == "manual":
            return getattr(chat_request, "character_mode", False)

        return False


# 为了向后兼容，保留旧名称
CharacterRuntimeDispatcher = CharacterRuntimeContextDispatcher
