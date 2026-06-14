"""群聊模式数据模型"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GroupConfig:
    """群聊配置"""

    speaker_strategy: str = "mention"  # round_robin / mention / relevance / random
    max_chars_per_turn: int = 800
    allow_character_cross_talk: bool = True
    shared_memory: bool = True
    token_budget: int = 4000
    auto_narrate: bool = True
    narrate_interval: int = 3  # 每 N 轮对话触发一次旁白

    def to_dict(self) -> dict[str, Any]:
        return {
            "speaker_strategy": self.speaker_strategy,
            "max_chars_per_turn": self.max_chars_per_turn,
            "allow_character_cross_talk": self.allow_character_cross_talk,
            "shared_memory": self.shared_memory,
            "token_budget": self.token_budget,
            "auto_narrate": self.auto_narrate,
            "narrate_interval": self.narrate_interval,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GroupConfig:
        return cls(
            speaker_strategy=data.get("speaker_strategy", "mention"),
            max_chars_per_turn=data.get("max_chars_per_turn", 800),
            allow_character_cross_talk=data.get("allow_character_cross_talk", True),
            shared_memory=data.get("shared_memory", True),
            token_budget=data.get("token_budget", 4000),
            auto_narrate=data.get("auto_narrate", True),
            narrate_interval=data.get("narrate_interval", 3),
        )


@dataclass
class InterCharacterRelation:
    """角色间关系"""

    char_a: str
    char_b: str
    familiarity: float = 0.0
    trust: float = 0.0
    affection: float = 0.0
    rivalry: float = 0.0
    history: list[dict[str, Any]] = field(default_factory=list)

    @property
    def relation_key(self) -> str:
        a, b = sorted([self.char_a, self.char_b])
        return f"{a}::{b}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "char_a": self.char_a,
            "char_b": self.char_b,
            "familiarity": self.familiarity,
            "trust": self.trust,
            "affection": self.affection,
            "rivalry": self.rivalry,
            "history": self.history[-50:],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InterCharacterRelation:
        return cls(
            char_a=data["char_a"],
            char_b=data["char_b"],
            familiarity=float(data.get("familiarity", 0)),
            trust=float(data.get("trust", 0)),
            affection=float(data.get("affection", 0)),
            rivalry=float(data.get("rivalry", 0)),
            history=data.get("history", []),
        )

    def update(self, dimension: str, delta: float, reason: str = "") -> None:
        current = getattr(self, dimension, 0.0)
        new_val = max(0.0, min(100.0, current + delta))
        setattr(self, dimension, new_val)
        self.history.append({
            "dimension": dimension,
            "delta": delta,
            "old": current,
            "new": new_val,
            "reason": reason,
            "ts": time.time(),
        })


@dataclass
class GroupConversation:
    """群聊会话"""

    group_id: str = ""
    name: str = ""
    character_ids: list[str] = field(default_factory=list)
    narrator_id: str | None = None
    active_speaker: str = ""
    speaker_queue: list[str] = field(default_factory=list)
    config: GroupConfig = field(default_factory=GroupConfig)
    turn_count: int = 0
    bound_channel: str = ""
    relations: dict[str, InterCharacterRelation] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def __post_init__(self):
        if not self.group_id:
            self.group_id = f"gc_{uuid.uuid4().hex[:12]}"

    def get_relation(self, char_a: str, char_b: str) -> InterCharacterRelation | None:
        a, b = sorted([char_a, char_b])
        key = f"{a}::{b}"
        return self.relations.get(key)

    def set_relation(self, relation: InterCharacterRelation) -> None:
        self.relations[relation.relation_key] = relation
        self.updated_at = time.time()

    def get_relation_matrix(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self.relations.values()]

    def advance_turn(self) -> None:
        self.turn_count += 1
        self.updated_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "name": self.name,
            "character_ids": self.character_ids,
            "narrator_id": self.narrator_id,
            "active_speaker": self.active_speaker,
            "speaker_queue": self.speaker_queue,
            "config": self.config.to_dict(),
            "turn_count": self.turn_count,
            "bound_channel": self.bound_channel,
            "relations": {k: v.to_dict() for k, v in self.relations.items()},
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GroupConversation:
        config = GroupConfig.from_dict(data.get("config", {}))
        relations = {}
        for k, v in (data.get("relations") or {}).items():
            relations[k] = InterCharacterRelation.from_dict(v)
        return cls(
            group_id=data.get("group_id", ""),
            name=data.get("name", ""),
            character_ids=data.get("character_ids", []),
            narrator_id=data.get("narrator_id"),
            active_speaker=data.get("active_speaker", ""),
            speaker_queue=data.get("speaker_queue", []),
            config=config,
            turn_count=data.get("turn_count", 0),
            bound_channel=data.get("bound_channel", ""),
            relations=relations,
            created_at=data.get("created_at", 0),
            updated_at=data.get("updated_at", 0),
        )
