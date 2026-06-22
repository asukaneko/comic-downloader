"""
Review Pipeline 数据模型

定义 Review 的输入/输出结构，与具体实现解耦。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReviewScore:
    """角色体验评分（0-1 浮点数）"""
    character_fidelity: float = 0.0    # 角色一致性
    immersion: float = 0.0             # 沉浸感
    relationship_progress: float = 0.0 # 关系推进
    story_progress: float = 0.0        # 剧情推进
    memory_value: float = 0.0          # 记忆价值
    world_consistency: float = 0.0     # 世界一致性
    user_engagement: float = 0.0       # 用户互动
    risk: float = 0.0                  # 风险评分

    def to_dict(self) -> dict[str, float]:
        return {
            "character_fidelity": self.character_fidelity,
            "immersion": self.immersion,
            "relationship_progress": self.relationship_progress,
            "story_progress": self.story_progress,
            "memory_value": self.memory_value,
            "world_consistency": self.world_consistency,
            "user_engagement": self.user_engagement,
            "risk": self.risk,
        }


@dataclass
class MemoryItem:
    """待写入的记忆条目"""
    target: str = "user"          # user / character / world
    mem_type: str = "short"       # short / long / relationship / event
    title: str = ""
    content: str = ""
    importance: float = 0.0
    ttl: str = "short"            # short / long / permanent


@dataclass
class RelationshipDelta:
    """关系变化结果"""
    affection: int = 0
    trust: int = 0
    familiarity: int = 0
    dependency: int = 0
    security: int = 0
    jealousy: int = 0
    reason: str = ""
    source: str = "review_pipeline"
    plot_node_id: str = ""
    conversation_id: str = ""


@dataclass
class PlotUpdate:
    """剧情更新建议"""
    should_create_node: bool = False
    level: str = "normal"         # normal / important / turning_point / ending
    summary: str = ""
    title: str = ""


@dataclass
class WorldBookUpdate:
    """世界书更新建议"""
    should_update: bool = False
    reason: str = ""
    entry_title: str = ""
    entry_content: str = ""


@dataclass
class OfflinePlotUpdate:
    """现实时间同步产生的离线剧情推进。"""

    should_inject: bool = False
    level: str = "none"           # same_day / days / long_absence
    elapsed_label: str = ""
    character_activity: str = ""
    world_changes: list[str] = field(default_factory=list)
    summary: str = ""
    prompt_text: str = ""


@dataclass
class ReviewInput:
    """Review Pipeline 输入"""
    conversation_id: str = ""
    character_id: str = ""
    user_id: str = ""
    group_id: str = ""
    user_message: str = ""
    assistant_message: str = ""
    recent_messages: list[dict[str, Any]] = field(default_factory=list)
    active_plot_node: dict[str, Any] | None = None
    selected_choice: dict[str, Any] | None = None
    relationship_state: dict[str, Any] = field(default_factory=dict)
    character_state: dict[str, Any] = field(default_factory=dict)
    world_context: dict[str, Any] = field(default_factory=dict)
    real_time_context: dict[str, Any] = field(default_factory=dict)
    plot_mode: bool = False
    plot_real_time_sync: bool = False
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ReviewOutput:
    """Review Pipeline 输出"""
    should_write_memory: bool = False
    memory_items: list[MemoryItem] = field(default_factory=list)
    relationship_delta: RelationshipDelta | None = None
    plot_update: PlotUpdate | None = None
    offline_plot_update: OfflinePlotUpdate | None = None
    world_book_update: WorldBookUpdate | None = None
    scores: ReviewScore | None = None
    source: str = "rule"          # rule / llm
    skipped: bool = False         # 普通闲聊跳过 Review

    def to_dict(self) -> dict[str, Any]:
        return {
            "should_write_memory": self.should_write_memory,
            "memory_items": [
                {
                    "target": m.target,
                    "mem_type": m.mem_type,
                    "title": m.title,
                    "content": m.content,
                    "importance": m.importance,
                    "ttl": m.ttl,
                }
                for m in self.memory_items
            ],
            "relationship_delta": {
                "affection": self.relationship_delta.affection,
                "trust": self.relationship_delta.trust,
                "familiarity": self.relationship_delta.familiarity,
                "dependency": self.relationship_delta.dependency,
                "security": self.relationship_delta.security,
                "jealousy": self.relationship_delta.jealousy,
                "reason": self.relationship_delta.reason,
            } if self.relationship_delta else None,
            "plot_update": {
                "should_create_node": self.plot_update.should_create_node,
                "level": self.plot_update.level,
                "summary": self.plot_update.summary,
                "title": self.plot_update.title,
            } if self.plot_update else None,
            "offline_plot_update": {
                "should_inject": self.offline_plot_update.should_inject,
                "level": self.offline_plot_update.level,
                "elapsed_label": self.offline_plot_update.elapsed_label,
                "character_activity": self.offline_plot_update.character_activity,
                "world_changes": list(self.offline_plot_update.world_changes),
                "summary": self.offline_plot_update.summary,
                "prompt_text": self.offline_plot_update.prompt_text,
            } if self.offline_plot_update else None,
            "world_book_update": {
                "should_update": self.world_book_update.should_update,
                "reason": self.world_book_update.reason,
            } if self.world_book_update else None,
            "scores": self.scores.to_dict() if self.scores else None,
            "source": self.source,
            "skipped": self.skipped,
        }
