"""
频道运行上下文和渲染策略

提供跨频道的统一上下文表示，用于角色运行时的输入输出适配。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChannelRuntimeContext:
    """统一频道运行上下文

    表达"这条消息来自哪个频道、哪个会话"，给记忆、角色状态、事件系统提供稳定 key。
    """

    channel: str
    """频道标识，如 web, qq, feishu, telegram"""

    conversation_id: str
    """会话 ID，用于记忆和状态隔离"""

    scene: str
    """场景类型: private / group / thread / web_session"""

    user_id: str = ""
    """用户 ID"""

    user_display_name: str = ""
    """用户显示名称"""

    group_id: str = ""
    """群组 ID（群聊场景）"""

    group_name: str = ""
    """群组名称"""

    thread_id: str = ""
    """话题/thread ID"""

    raw_event_id: str = ""
    """原始事件 ID"""

    metadata: dict[str, Any] = field(default_factory=dict)
    """扩展元数据"""

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        return {
            "channel": self.channel,
            "conversation_id": self.conversation_id,
            "scene": self.scene,
            "user_id": self.user_id,
            "user_display_name": self.user_display_name,
            "group_id": self.group_id,
            "group_name": self.group_name,
            "thread_id": self.thread_id,
            "raw_event_id": self.raw_event_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChannelRuntimeContext:
        """从字典反序列化"""
        return cls(
            channel=data.get("channel", ""),
            conversation_id=data.get("conversation_id", ""),
            scene=data.get("scene", "private"),
            user_id=data.get("user_id", ""),
            user_display_name=data.get("user_display_name", ""),
            group_id=data.get("group_id", ""),
            group_name=data.get("group_name", ""),
            thread_id=data.get("thread_id", ""),
            raw_event_id=data.get("raw_event_id", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ChannelRenderPolicy:
    """频道输出渲染策略

    描述频道的输出能力，角色运行时只产出抽象结果，频道适配器负责渲染。
    """

    supports_stream: bool = False
    """是否支持流式输出"""

    supports_markdown: bool = True
    """是否支持 Markdown"""

    supports_image: bool = False
    """是否支持图片"""

    supports_file: bool = False
    """是否支持文件"""

    supports_quote_reply: bool = False
    """是否支持引用回复"""

    supports_at: bool = False
    """是否支持 @ 提及"""

    max_text_length: int | None = None
    """单条消息最大文本长度"""

    split_strategy: str = "paragraph"
    """分段策略: paragraph / sentence / fixed_length / none"""

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        return {
            "supports_stream": self.supports_stream,
            "supports_markdown": self.supports_markdown,
            "supports_image": self.supports_image,
            "supports_file": self.supports_file,
            "supports_quote_reply": self.supports_quote_reply,
            "supports_at": self.supports_at,
            "max_text_length": self.max_text_length,
            "split_strategy": self.split_strategy,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChannelRenderPolicy:
        """从字典反序列化"""
        return cls(
            supports_stream=data.get("supports_stream", False),
            supports_markdown=data.get("supports_markdown", True),
            supports_image=data.get("supports_image", False),
            supports_file=data.get("supports_file", False),
            supports_quote_reply=data.get("supports_quote_reply", False),
            supports_at=data.get("supports_at", False),
            max_text_length=data.get("max_text_length"),
            split_strategy=data.get("split_strategy", "paragraph"),
        )
