"""群聊发言调度器"""

from __future__ import annotations

import logging
import random as _random
import re
from typing import Any

from nbot.group.models import GroupConversation

_log = logging.getLogger(__name__)


class SpeakerScheduler:
    """发言调度器：决定下一个发言的角色"""

    _instance: SpeakerScheduler | None = None

    @classmethod
    def instance(cls) -> SpeakerScheduler:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def decide_next_speaker(
        self,
        conversation: GroupConversation,
        message: str,
        character_ids: list[str],
        *,
        last_speaker: str = "",
    ) -> str:
        """决定下一个发言角色"""
        if not character_ids:
            return ""

        strategy = conversation.config.speaker_strategy

        if strategy == "round_robin":
            return self._round_robin(conversation, character_ids, last_speaker)
        if strategy == "mention":
            return self._mention(message, character_ids)
        if strategy == "random":
            return self._random(character_ids)
        if strategy == "relevance":
            return self._relevance(message, character_ids, conversation)
        if strategy == "narrator_driven":
            return self._narrator_driven(conversation, character_ids)

        _log.warning("unknown speaker strategy: %s, falling back to mention", strategy)
        return self._mention(message, character_ids)

    def should_respond(
        self,
        conversation: GroupConversation,
        message: str,
        character_id: str,
    ) -> bool:
        """判断指定角色是否应该回复"""
        strategy = conversation.config.speaker_strategy

        # mention 策略：只在被 @ 时回复
        if strategy == "mention":
            return self._is_mentioned(message, character_id)

        # 其他策略：由 decide_next_speaker 决定
        return True

    def build_group_system_prompt(
        self,
        conversation: GroupConversation,
        character_profiles: dict[str, dict[str, Any]],
        speaker_id: str,
        *,
        extra_context: str = "",
    ) -> str:
        """构建群聊 system prompt"""
        lines = [
            "# 群聊场景",
            f"群聊名称: {conversation.name}",
            f"当前发言角色: {speaker_id}",
            "",
            "## 参与角色",
        ]

        for cid, profile in character_profiles.items():
            name = profile.get("name", cid)
            desc = profile.get("description", "")
            personality = profile.get("personality", "")
            lines.append(f"- **{name}** ({cid}): {desc[:80]}")
            if personality:
                lines.append(f"  性格: {personality[:60]}")

        # 关系矩阵
        relations = conversation.get_relation_matrix()
        if relations:
            lines.extend(["", "## 角色间关系"])
            for r in relations:
                parts = []
                if r["familiarity"] > 0:
                    parts.append(f"熟悉度={r['familiarity']:.0f}")
                if r["trust"] > 0:
                    parts.append(f"信任={r['trust']:.0f}")
                if r["affection"] > 0:
                    parts.append(f"好感={r['affection']:.0f}")
                if r["rivalry"] > 0:
                    parts.append(f"竞争={r['rivalry']:.0f}")
                if parts:
                    lines.append(f"- {r['char_a']} <-> {r['char_b']}: {', '.join(parts)}")

        # 发言规则
        lines.extend([
            "",
            "## 群聊规则",
            f"- 你现在扮演 {speaker_id}，以该角色的身份和口吻回复",
            "- 回复要简洁自然，符合角色性格",
            "- 可以引用其他角色的话，但不要代替其他角色发言",
            "- 保持角色一致性，不要跳出设定",
        ])

        if extra_context:
            lines.extend(["", extra_context])

        return chr(10).join(lines)

    def _round_robin(
        self,
        conversation: GroupConversation,
        character_ids: list[str],
        last_speaker: str,
    ) -> str:
        if not last_speaker or last_speaker not in character_ids:
            return character_ids[0]
        idx = character_ids.index(last_speaker)
        return character_ids[(idx + 1) % len(character_ids)]

    def _mention(self, message: str, character_ids: list[str]) -> str:
        """检测消息中 @角色名 或提到角色名"""
        lower_msg = message.lower()
        for cid in character_ids:
            if self._is_mentioned(message, cid):
                return cid
        # 没有明确 @，返回第一个角色
        return character_ids[0] if character_ids else ""

    def _is_mentioned(self, message: str, character_id: str) -> bool:
        """检测角色是否被提及"""
        lower_msg = message.lower()
        # 检查 @角色名 模式
        if f"@{character_id.lower()}" in lower_msg:
            return True
        # 检查角色名直接出现
        if character_id.lower() in lower_msg:
            return True
        return False

    def _random(self, character_ids: list[str]) -> str:
        return _random.choice(character_ids)

    def _narrator_driven(self, conversation: GroupConversation, character_ids: list[str]) -> str:
        """旁白驱动策略：由旁白角色 ID 决定（简化版：返回 narrator_id 或随机）"""
        narrator_id = conversation.narrator_id
        if narrator_id and narrator_id in character_ids:
            return narrator_id
        # 旁白不在角色列表中时，返回第一个非旁白角色
        non_narrator = [c for c in character_ids if c != narrator_id]
        return non_narrator[0] if non_narrator else _random.choice(character_ids)

    def _relevance(self, message: str, character_ids: list[str], conversation=None) -> str:
        """基于相关度打分：关键词匹配 + 关系加成"""
        scores: dict[str, float] = {}
        lower_msg = message.lower()
        for cid in character_ids:
            scores[cid] = lower_msg.count(cid.lower()) * 10.0

        # 关系加成：高 affinity 的角色更容易接话
        if conversation and hasattr(conversation, 'relations'):
            for cid in character_ids:
                for rel in conversation.relations.values():
                    if rel.char_a == cid or rel.char_b == cid:
                        scores[cid] = scores.get(cid, 0) + rel.affection * 0.05
                        scores[cid] = scores.get(cid, 0) + rel.familiarity * 0.03

        if max(scores.values()) > 0:
            return max(scores, key=scores.get)
        return _random.choice(character_ids)
