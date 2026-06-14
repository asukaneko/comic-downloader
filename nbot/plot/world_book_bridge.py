"""剧情世界书桥接 — 转折点写入世界书"""

from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger(__name__)


class PlotWorldBookBridge:
    """将转折点剧情写入世界书条目"""

    _instance: PlotWorldBookBridge | None = None

    @classmethod
    def instance(cls) -> PlotWorldBookBridge:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def on_turning_point(
        self,
        choice: Any,
        conversation_id: str,
        character_id: str,
        book_id: str = "",
        world_book_store: Any = None,
    ) -> bool:
        """转折点选项写入世界书"""
        if world_book_store is None:
            _log.debug("world book store unavailable, skip")
            return False
        if not book_id:
            _log.debug("no book_id specified, skip")
            return False

        text = getattr(choice, "text", "")
        intent = getattr(choice, "intent", "")

        # 从 intent 提取关键词
        keywords = self._extract_keywords(text, intent)

        entry_data = {
            "name": f"[剧情转折] {text[:30]}",
            "content": f"剧情转折点: {text}" + chr(10) + f"意图: {intent}" + chr(10) + f"会话: {conversation_id}",
            "keywords": keywords,
            "entry_type": "event",
            "priority": 80,
            "always_on": False,
            "tags": ["plot", "turning_point"],
        }

        try:
            entry = world_book_store.add_entry(book_id, entry_data)
            if entry:
                _log.info("plot world book entry added: %s", entry.name)
                return True
            _log.warning("failed to add world book entry to book %s", book_id)
            return False
        except Exception as e:
            _log.error("plot world book entry failed: %s", e)
            return False

    @staticmethod
    def _extract_keywords(text: str, intent: str) -> list[str]:
        """从文本中提取关键词（简化版）"""
        import re
        combined = text + " " + intent
        # 提取中文词组（2-4字）
        cn_words = re.findall(r"[一-鿿]{2,4}", combined)
        # 去重，取前5个
        seen = set()
        keywords = []
        for w in cn_words:
            if w not in seen and len(w) >= 2:
                seen.add(w)
                keywords.append(w)
                if len(keywords) >= 5:
                    break
        return keywords
