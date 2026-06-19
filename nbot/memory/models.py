"""
MemoryFile 数据模型

代表 MemoryFS 中的一个逻辑记忆文件。
这些"文件"不一定真实落盘，而是对底层记忆条目的逻辑组织。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class MemoryFile:
    """逻辑记忆文件，对应角色记忆系统中一个有语义的维度。

    path 规范（使用 / 分隔，不含前导 /）：
        characters/{char_id}/general.md
        characters/{char_id}/users/{user_id}.md
        characters/{char_id}/diary/daily.md
        characters/{char_id}/diary/weekly.md
        characters/{char_id}/relationships/{target_char_id}.md
        characters/{char_id}/plot/{conversation_id}.md
        characters/{char_id}/world/events.md
    """

    path: str
    character_id: str
    target_id: str = ""           # 关联的用户 ID 或角色 ID
    title: str = ""
    content: str = ""             # 当前聚合后的文本内容
    summary: str = ""             # 简短摘要（用于 prompt 注入）
    tags: List[str] = field(default_factory=list)
    importance: float = 0.0       # 0-1，越高越优先读取
    version: int = 1              # 每次更新递增
    source_event_id: str = ""     # 触发本次写入的事件 ID
    memory_ids: List[str] = field(default_factory=list)  # 关联的底层记忆 ID
    updated_at: str = ""

    def __post_init__(self):
        if not self.updated_at:
            self.updated_at = _now_iso()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "character_id": self.character_id,
            "target_id": self.target_id,
            "title": self.title,
            "content": self.content,
            "summary": self.summary,
            "tags": self.tags,
            "importance": self.importance,
            "version": self.version,
            "source_event_id": self.source_event_id,
            "memory_ids": self.memory_ids,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryFile":
        return cls(
            path=data.get("path", ""),
            character_id=data.get("character_id", ""),
            target_id=data.get("target_id", ""),
            title=data.get("title", ""),
            content=data.get("content", ""),
            summary=data.get("summary", ""),
            tags=data.get("tags", []) or [],
            importance=data.get("importance", 0.0),
            version=data.get("version", 1),
            source_event_id=data.get("source_event_id", ""),
            memory_ids=data.get("memory_ids", []) or [],
            updated_at=data.get("updated_at", ""),
        )

    def to_prompt_text(self) -> str:
        """生成适合注入 prompt 的简短文本。优先用 summary，否则截断 content。"""
        text = self.summary or self.content
        if len(text) > 500:
            text = text[:497] + "..."
        return f"[{self.title or self.path}]\n{text}" if text else ""
