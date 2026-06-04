"""
角色频道适配器协议

定义频道接入角色运行时所需实现的最小接口。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from nbot.character.channel_context import ChannelRenderPolicy, ChannelRuntimeContext
from nbot.character.runtime_request import CharacterRuntimeResult


@runtime_checkable
class CharacterChannelAdapter(Protocol):
    """角色频道适配器协议

    频道实现此协议即可接入角色运行时，无需修改角色运行时核心代码。

    实现步骤：
    1. 继承 BaseChannelAdapter 和本协议
    2. 实现 build_runtime_context - 构建频道运行上下文
    3. 实现 get_render_policy - 返回频道输出策略
    4. 实现 select_character_id - 选择角色卡
    5. 实现 resolve_memory_scope - 确定记忆作用域
    6. 实现 render_result - 渲染角色运行结果为频道消息格式
    """

    channel_name: str
    """频道标识，如 qq, feishu, telegram"""

    def build_runtime_context(self, chat_request: Any) -> ChannelRuntimeContext:
        """从 ChatRequest 构建频道运行上下文

        Args:
            chat_request: 原始聊天请求

        Returns:
            ChannelRuntimeContext 实例
        """
        ...

    def get_render_policy(self, context: ChannelRuntimeContext) -> ChannelRenderPolicy:
        """获取频道输出渲染策略

        Args:
            context: 频道运行上下文

        Returns:
            ChannelRenderPolicy 实例
        """
        ...

    def select_character_id(self, context: ChannelRuntimeContext) -> str | None:
        """选择要使用的角色卡 ID

        Args:
            context: 频道运行上下文

        Returns:
            角色卡 ID，None 表示使用默认角色
        """
        ...

    def resolve_memory_scope(self, context: ChannelRuntimeContext) -> str:
        """确定记忆作用域

        Args:
            context: 频道运行上下文

        Returns:
            作用域标识，如 conversation, user, group, group_user, chat_user, thread
        """
        ...

    def render_result(
        self,
        result: CharacterRuntimeResult,
        context: ChannelRuntimeContext,
    ) -> list[dict[str, Any]]:
        """渲染角色运行结果为频道消息格式

        Args:
            result: 角色运行结果
            context: 频道运行上下文

        Returns:
            消息列表，每个消息为 dict，包含 type 和 content 等字段
        """
        ...
