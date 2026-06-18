"""
Plot System 数据模型

定义故事节点、分支选择、边等数据结构。
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PlotNode:
    """故事节点，代表剧情中的一个关键时刻"""

    conversation_id: str
    character_id: str
    title: str
    summary: str
    level: str  # normal / important / turning_point / ending
    scene: Dict[str, Any] = field(default_factory=dict)
    state_snapshot: Dict[str, Any] = field(default_factory=dict)
    relationship_snapshot: Dict[str, Any] = field(default_factory=dict)

    # 可选字段
    id: str = ""
    parent_node_id: str = ""
    selected_choice_id: str = ""
    created_at: str = ""

    # 会话内分支：该轮的消息快照（用于物化任意分支的完整对话）
    user_message: Dict[str, Any] = field(default_factory=dict)
    assistant_message: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = _new_id("pn")
        if not self.created_at:
            self.created_at = _now_iso()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "character_id": self.character_id,
            "title": self.title,
            "summary": self.summary,
            "level": self.level,
            "scene": self.scene,
            "state_snapshot": self.state_snapshot,
            "relationship_snapshot": self.relationship_snapshot,
            "parent_node_id": self.parent_node_id,
            "selected_choice_id": self.selected_choice_id,
            "created_at": self.created_at,
            "user_message": self.user_message,
            "assistant_message": self.assistant_message,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlotNode":
        return cls(
            id=data.get("id", ""),
            conversation_id=data.get("conversation_id", ""),
            character_id=data.get("character_id", ""),
            title=data.get("title", ""),
            summary=data.get("summary", ""),
            level=data.get("level", "normal"),
            scene=data.get("scene", {}),
            state_snapshot=data.get("state_snapshot", {}),
            relationship_snapshot=data.get("relationship_snapshot", {}),
            parent_node_id=data.get("parent_node_id", ""),
            selected_choice_id=data.get("selected_choice_id", ""),
            created_at=data.get("created_at", ""),
            user_message=data.get("user_message", {}) or {},
            assistant_message=data.get("assistant_message", {}) or {},
        )


@dataclass
class PlotChoice:
    """分支选择，代表玩家在某个节点可做的决定"""

    node_id: str
    text: str
    level: str  # normal / important / turning_point / ending / hidden

    # 可选字段
    id: str = ""
    intent: str = ""
    selected: bool = False
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = _new_id("pc")
        if not self.created_at:
            self.created_at = _now_iso()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "node_id": self.node_id,
            "text": self.text,
            "level": self.level,
            "intent": self.intent,
            "selected": self.selected,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlotChoice":
        return cls(
            id=data.get("id", ""),
            node_id=data.get("node_id", ""),
            text=data.get("text", ""),
            level=data.get("level", "normal"),
            intent=data.get("intent", ""),
            selected=data.get("selected", False),
            created_at=data.get("created_at", ""),
        )


@dataclass
class PlotEdge:
    """故事边，连接两个节点并记录触发边的选择"""

    from_node_id: str
    to_node_id: str
    choice_id: str

    # 可选字段
    id: str = ""
    label: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = _new_id("pe")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "from_node_id": self.from_node_id,
            "to_node_id": self.to_node_id,
            "choice_id": self.choice_id,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlotEdge":
        return cls(
            id=data.get("id", ""),
            from_node_id=data.get("from_node_id", ""),
            to_node_id=data.get("to_node_id", ""),
            choice_id=data.get("choice_id", ""),
            label=data.get("label", ""),
        )
