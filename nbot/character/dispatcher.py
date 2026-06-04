"""
角色运行时统一调度器

协调频道适配器和角色运行时，提供统一的角色运行入口。
"""

from __future__ import annotations

import logging
from typing import Any

from nbot.character.channel_adapter import CharacterChannelAdapter
from nbot.character.channel_context import ChannelRuntimeContext
from nbot.character.runtime import CharacterRuntime
from nbot.character.runtime_request import CharacterRuntimeRequest, CharacterRuntimeResult

logger = logging.getLogger(__name__)


class CharacterRuntimeDispatcher:
    """角色运行时统一调度器

    职责：
    1. 根据频道找到对应的适配器
    2. 构造统一角色运行上下文
    3. 判断该频道是否启用角色进行时
    4. 选择角色卡和记忆作用域
    5. 调用角色运行时
    6. 将结果交给频道适配器渲染
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

    def is_enabled(self, context: ChannelRuntimeContext) -> bool:
        """检查频道是否启用角色运行时

        Args:
            context: 频道运行上下文

        Returns:
            是否启用
        """
        channel_config = self._config.get("channels", {}).get(context.channel, {})
        runtime_config = channel_config.get("character_runtime", {})

        # 检查频道级别开关
        if not runtime_config.get("enabled", False):
            return False

        # 检查全局默认开关
        global_config = self._config.get("character_runtime", {})
        if not global_config.get("default_enabled", True):
            # 全局关闭时，需要频道显式开启
            return runtime_config.get("enabled", False)

        return True

    def get_trigger_strategy(self, context: ChannelRuntimeContext) -> str:
        """获取触发策略

        Args:
            context: 频道运行上下文

        Returns:
            触发策略: always, private_only, mention_only, mention_or_private, keyword, manual
        """
        channel_config = self._config.get("channels", {}).get(context.channel, {})
        runtime_config = channel_config.get("character_runtime", {})
        return runtime_config.get("trigger", "always")

    def get_memory_scope(self, context: ChannelRuntimeContext) -> str:
        """获取记忆作用域

        Args:
            context: 频道运行上下文

        Returns:
            作用域: conversation, user, group, group_user, chat_user, thread
        """
        channel_config = self._config.get("channels", {}).get(context.channel, {})
        runtime_config = channel_config.get("character_runtime", {})
        return runtime_config.get("memory_scope", "conversation")

    def get_default_character_id(self, context: ChannelRuntimeContext) -> str:
        """获取默认角色卡 ID

        Args:
            context: 频道运行上下文

        Returns:
            角色卡 ID
        """
        channel_config = self._config.get("channels", {}).get(context.channel, {})
        runtime_config = channel_config.get("character_runtime", {})
        return runtime_config.get(
            "default_character_id",
            self._config.get("character_runtime", {}).get("default_character_id", ""),
        )

    async def dispatch(
        self,
        chat_request: Any,
        channel: str,
    ) -> CharacterRuntimeResult | None:
        """调度角色运行

        Args:
            chat_request: 原始聊天请求
            channel: 频道标识

        Returns:
            角色运行结果，未启用或出错时返回 None
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

        # 7. 获取渲染策略
        render_policy = adapter.get_render_policy(context)

        # 8. 构建角色运行请求
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
                "render_policy": render_policy.to_dict(),
            },
        )

        # 9. 调用角色运行时
        try:
            result = await self._run_runtime(request)
            return result
        except Exception:
            logger.exception("Character runtime error for channel: %s", channel)
            return None

    async def _run_runtime(
        self,
        request: CharacterRuntimeRequest,
    ) -> CharacterRuntimeResult:
        """执行角色运行时

        Args:
            request: 角色运行请求

        Returns:
            角色运行结果
        """
        from nbot.character.models import CharacterIdentity

        # 构建 CharacterIdentity
        identity = CharacterIdentity(
            character_id=request.character_id or "",
            target_id=request.user_id,
            scope_id=request.context.conversation_id,
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

        # 构建结果（实际的 AI 调用由上层 Pipeline 完成）
        # 这里返回的是角色运行时的上下文信息
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

        if trigger == "keyword":
            keywords = self._config.get("channels", {}).get(
                context.channel, {}
            ).get("character_runtime", {}).get("trigger_keywords", [])
            content = getattr(chat_request, "content", "")
            return any(kw in content for kw in keywords)

        if trigger == "manual":
            return getattr(chat_request, "character_mode", False)

        return False
