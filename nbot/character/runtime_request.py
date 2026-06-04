"""
角色运行请求和结果

定义跨频道的统一角色运行输入输出结构。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nbot.character.channel_context import ChannelRuntimeContext


@dataclass
class CharacterRuntimeRequest:
    """角色运行请求

    所有频道都把输入转换成这个结构，角色运行时只依赖这个结构，不感知具体平台。
    """

    context: ChannelRuntimeContext
    """频道运行上下文"""

    content: str
    """用户消息内容"""

    sender: str
    """发送者显示名称"""

    user_id: str = ""
    """用户 ID"""

    attachments: list[dict[str, Any]] = field(default_factory=list)
    """附件列表"""

    character_id: str | None = None
    """指定角色卡 ID，None 表示使用默认"""

    parent_message_id: str | None = None
    """父消息 ID（引用回复场景）"""

    metadata: dict[str, Any] = field(default_factory=dict)
    """扩展元数据，可包含 memory_scope, render_policy 等"""

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        return {
            "context": self.context.to_dict(),
            "content": self.content,
            "sender": self.sender,
            "user_id": self.user_id,
            "attachments": self.attachments,
            "character_id": self.character_id,
            "parent_message_id": self.parent_message_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CharacterRuntimeRequest:
        """从字典反序列化"""
        return cls(
            context=ChannelRuntimeContext.from_dict(data.get("context", {})),
            content=data.get("content", ""),
            sender=data.get("sender", ""),
            user_id=data.get("user_id", ""),
            attachments=data.get("attachments", []),
            character_id=data.get("character_id"),
            parent_message_id=data.get("parent_message_id"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class CharacterRuntimeResult:
    """角色运行结果

    统一角色输出，频道适配器根据自身能力渲染结果。
    """

    text: str
    """AI 回复文本"""

    assistant_message: dict[str, Any]
    """完整的 assistant 消息（包含 role, content 等）"""

    memory_updates: list[dict[str, Any]] = field(default_factory=list)
    """记忆更新列表"""

    events: list[dict[str, Any]] = field(default_factory=list)
    """事件列表"""

    tool_call_history: list[dict[str, Any]] = field(default_factory=list)
    """工具调用历史"""

    state_patch: dict[str, Any] = field(default_factory=dict)
    """状态补丁（情绪、关系变化等）"""

    metadata: dict[str, Any] = field(default_factory=dict)
    """扩展元数据"""

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        return {
            "text": self.text,
            "assistant_message": self.assistant_message,
            "memory_updates": self.memory_updates,
            "events": self.events,
            "tool_call_history": self.tool_call_history,
            "state_patch": self.state_patch,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CharacterRuntimeResult:
        """从字典反序列化"""
        return cls(
            text=data.get("text", ""),
            assistant_message=data.get("assistant_message", {}),
            memory_updates=data.get("memory_updates", []),
            events=data.get("events", []),
            tool_call_history=data.get("tool_call_history", []),
            state_patch=data.get("state_patch", {}),
            metadata=data.get("metadata", {}),
        )
