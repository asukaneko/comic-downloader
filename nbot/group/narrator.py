"""旁白角色 - 第三人称场景描述"""

from __future__ import annotations

import logging
import time
from typing import Any

_log = logging.getLogger(__name__)

# 旁白触发条件枚举
NARRATE_TRIGGERS = {
    "scene_change": "场景切换",
    "character_join": "新角色加入",
    "plot_node": "剧情节点",
    "silence": "长时间沉默",
    "interval": "周期触发",
    "manual": "手动触发",
}

# 默认旁白 prompt 模板
_NARRATE_PROMPT = """你是一个旁白叙述者。根据当前场景信息，用简洁的第三人称描述场景氛围、环境或角色状态。

规则：
- 只描述，不参与对话
- 使用第三人称（他/她/他们）
- 保持简短（2-4句话）
- 不要重复已知信息
- 语气中立客观

当前场景：{scene_context}
触发原因：{trigger_desc}
最近对话摘要：{recent_summary}
"""


class NarratorCharacter:
    """旁白角色：为群聊场景提供第三人称叙述"""

    _instance: NarratorCharacter | None = None

    @classmethod
    def instance(cls) -> NarratorCharacter:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._last_narrate_time: float = 0.0
        self._turns_since_narrate: int = 0
        self._enabled: bool = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    def should_narrate(
        self,
        trigger: str,
        turn_count: int,
        *,
        narrate_interval: int = 3,
    ) -> bool:
        """判断是否应该生成旁白"""
        if not self._enabled:
            return False

        # 立即触发的条件
        if trigger in ("scene_change", "character_join", "plot_node", "manual"):
            return True

        # 周期触发
        if trigger == "interval":
            self._turns_since_narrate += 1
            if self._turns_since_narrate >= narrate_interval:
                self._turns_since_narrate = 0
                return True

        # 沉默触发
        if trigger == "silence":
            elapsed = time.time() - self._last_narrate_time
            if elapsed > 300:  # 5 分钟
                return True

        return False

    def build_narrate_prompt(
        self,
        trigger: str,
        scene_context: str,
        recent_summary: str,
    ) -> str:
        """构建旁白生成 prompt"""
        trigger_desc = NARRATE_TRIGGERS.get(trigger, trigger)
        return _NARRATE_PROMPT.format(
            scene_context=scene_context,
            trigger_desc=trigger_desc,
            recent_summary=recent_summary,
        )

    def format_narration(self, text: str) -> str:
        """格式化旁白输出"""
        # 清理多余空白
        text = text.strip()
        # 移除可能的前缀标记
        for prefix in ["[旁白]", "旁白：", "旁白:", "Narrator:", "narrator:"]:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
        return text

    def mark_narrated(self) -> None:
        """标记已生成旁白"""
        self._last_narrate_time = time.time()
        self._turns_since_narrate = 0

    def build_scene_context(
        self,
        character_names: list[str],
        location: str = "",
        atmosphere: str = "",
    ) -> str:
        """构建场景上下文描述"""
        parts = []
        if location:
            parts.append(f"地点: {location}")
        if character_names:
            joined = ", ".join(character_names)
            parts.append(f"在场角色: {joined}")
        if atmosphere:
            parts.append(f"氛围: {atmosphere}")
        return " | ".join(parts) if parts else "未知场景"

    def build_recent_summary(self, messages: list[dict[str, Any]], max_chars: int = 300) -> str:
        """从最近消息中提取摘要"""
        if not messages:
            return "暂无对话"
        recent = messages[-5:]
        lines = []
        for msg in recent:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if len(content) > 80:
                content = content[:80] + "..."
            lines.append(f"{role}: {content}")
        summary = chr(10).join(lines)
        if len(summary) > max_chars:
            summary = summary[:max_chars] + "..."
        return summary
