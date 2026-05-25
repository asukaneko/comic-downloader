"""节点能力声明系统

定义 Gateway 节点可以声明的能力类型：

频道能力（Channel Capability）：
- 每个频道适配器声明自己支持的能力
- 例如：webhook 接入、消息发送、富文本、文件上传等

工具能力（Tool Capability）：
- AI Core 可用的工具集
- 例如：搜索、代码执行、图片生成等

能力用于：
1. Node 注册时声明自己的能力
2. 路由时选择有对应能力的 Node
3. 控制台展示可用能力列表
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

_log = logging.getLogger(__name__)


class ChannelCapability(str, Enum):
    """预定义的频道能力"""

    # 基础消息
    WEBHOOK_RECEIVE = "channel.webhook.receive"
    MESSAGE_SEND = "channel.message.send"
    MESSAGE_EDIT = "channel.message.edit"
    MESSAGE_DELETE = "channel.message.delete"
    MESSAGE_RECALL = "channel.message.recall"

    # 富文本
    MARKDOWN_SUPPORT = "channel.markdown"
    RICH_TEXT = "channel.rich_text"
    HTML_RENDER = "channel.html_render"

    # 媒体
    IMAGE_SEND = "channel.image.send"
    IMAGE_UPLOAD = "channel.image.upload"
    FILE_SEND = "channel.file.send"
    FILE_UPLOAD = "channel.file.upload"
    VOICE_MESSAGE = "channel.voice.message"
    VIDEO_MESSAGE = "channel.video.message"

    # 交互
    REACTION_ADD = "channel.reaction.add"
    REACTION_REMOVE = "channel.reaction.remove"
    KEYBOARD_INLINE = "channel.keyboard.inline"
    KEYBOARD_REPLY = "channel.keyboard.reply"

    # 群组管理
    GROUP_INFO = "channel.group.info"
    GROUP_MEMBERS = "channel.group.members"
    GROUP_KICK = "channel.group.kick"
    GROUP_BAN = "channel.group.ban"
    GROUP_MUTE = "channel.group.mute"

    # 会话
    CONVERSATION_LIST = "channel.conversation.list"
    CONVERSATION_HISTORY = "channel.conversation.history"
    TYPING_INDICATOR = "channel.typing.indicator"


class ToolCapability(str, Enum):
    """预定义的工具能力"""

    # 信息获取
    WEB_SEARCH = "tool.web_search"
    CODE_EXECUTION = "tool.code_execution"
    CALCULATOR = "tool.calculator"

    # 内容生成
    IMAGE_GENERATION = "tool.image_generation"
    TEXT_TO_SPEECH = "tool.text_to_speech"
    SPEECH_TO_TEXT = "tool.speech_to_text"
    TRANSLATION = "tool.translation"

    # 外部集成
    WEATHER_QUERY = "tool.weather"
    MAP_SEARCH = "tool.map_search"
    NEWS_FETCH = "tool.news_fetch"
    STOCK_QUERY = "tool.stock_query"

    # 文件操作
    FILE_READ = "tool.file_read"
    FILE_WRITE = "tool.file_write"
    PDF_PARSE = "tool.pdf_parse"

    # 数据库
    DATABASE_QUERY = "tool.database_query"
    KNOWLEDGE_SEARCH = "tool.knowledge_search"


@dataclass
class CapabilityDeclaration:
    """能力声明

    用于 Node 注册或频道适配器声明自身能力。
    """

    capability_type: str  # "channel" 或 "tool"
    capability_id: str
    version: str = "1.0.0"
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.capability_type,
            "id": self.capability_id,
            "version": self.version,
            "description": self.description,
            "parameters": self.parameters,
            "metadata": self.metadata,
        }


@dataclass
class NodeCapabilities:
    """节点的完整能力集合"""

    node_id: str = ""
    channel_capabilities: list[CapabilityDeclaration] = field(default_factory=list)
    tool_capabilities: list[CapabilityDeclaration] = field(default_factory=list)

    def has_channel_capability(self, capability_id: str) -> bool:
        return any(c.capability_id == capability_id for c in self.channel_capabilities)

    def has_tool_capability(self, capability_id: str) -> bool:
        return any(c.capability_id == capability_id for c in self.tool_capabilities)

    def add_channel(self, declaration: CapabilityDeclaration) -> None:
        declaration.capability_type = "channel"
        if not any(c.capability_id == declaration.capability_id for c in self.channel_capabilities):
            self.channel_capabilities.append(declaration)

    def add_tool(self, declaration: CapabilityDeclaration) -> None:
        declaration.capability_type = "tool"
        if not any(c.capability_id == declaration.capability_id for c in self.tool_capabilities):
            self.tool_capabilities.append(declaration)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "channels": [c.to_dict() for c in self.channel_capabilities],
            "tools": [c.to_dict() for c in self.tool_capabilities],
        }


# 预定义的能力映射表（用于快速查找）
CHANNEL_CAPABILITY_MAP: dict[str, str] = {
    c.value: c.name.replace("_", " ").title()
    for c in ChannelCapability
}

TOOL_CAPABILITY_MAP: dict[str, str] = {
    c.value: c.name.replace("_", " ").title()
    for c in ToolCapability
}
