"""剧情记忆桥接 — 重要选项自动写入记忆"""

from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger(__name__)

# 选项等级到记忆类型的映射
_LEVEL_MEM_TYPE = {
    "important": "relationship",
    "turning_point": "event",
    "ending": "long",
}


class PlotMemoryBridge:
    """将剧情选择写入角色记忆"""

    _instance: PlotMemoryBridge | None = None

    @classmethod
    def instance(cls) -> PlotMemoryBridge:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def on_choice_selected(
        self,
        choice: Any,
        conversation_id: str,
        character_id: str,
        user_id: str = "",
        memory_service: Any = None,
    ) -> bool:
        """选择被选中后，按等级写入记忆"""
        if memory_service is None:
            _log.debug("memory service unavailable, skip")
            return False

        level = getattr(choice, "level", "normal")
        mem_type = _LEVEL_MEM_TYPE.get(level)
        if mem_type is None:
            # normal 级别不写入记忆
            return False

        text = getattr(choice, "text", "")
        intent = getattr(choice, "intent", "")
        title = f"[剧情] {text[:50]}"
        content = f"剧情选择: {text}"
        if intent:
            content += chr(10) + f"意图: {intent}"

        try:
            memory_service.save(
                character_id=character_id,
                target_id=user_id or conversation_id,
                title=title,
                content=content,
                summary=text[:100],
                mem_type=mem_type,
            )
            _log.info("plot memory saved: level=%s title=%s", level, title)
            return True
        except Exception as e:
            _log.error("plot memory save failed: %s", e)
            return False
