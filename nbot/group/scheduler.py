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
        group_context: dict[str, Any] | None = None,
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
        if strategy == "world_engine":
            return self._world_engine(
                message, character_ids, conversation,
                last_speaker=last_speaker,
                group_context=group_context or {},
            )

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
        full_profile: Any = None,
    ) -> str:
        """构建群聊 system prompt

        Args:
            full_profile: 当前发言角色的完整 CharacterProfile 对象（可选）
        """
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

        # 当前发言角色的完整角色卡
        if full_profile:
            lines.extend(["", "## 当前发言角色设定"])
            system_prompt = getattr(full_profile, "system_prompt", "")
            if system_prompt:
                # system_prompt 已包含完整设定，直接使用
                lines.append(system_prompt)
            else:
                # 没有 system_prompt 时，单独添加各字段
                if getattr(full_profile, "basic_info", ""):
                    lines.append(f"【基本信息】\n{full_profile.basic_info}")
                if getattr(full_profile, "personality", ""):
                    lines.append(f"【性格特点】\n{full_profile.personality}")
                if getattr(full_profile, "scenario", ""):
                    lines.append(f"【场景设定】\n{full_profile.scenario}")
                if getattr(full_profile, "first_message", ""):
                    lines.append(f"【开场白】\n{full_profile.first_message}")
                if getattr(full_profile, "example_dialogues", ""):
                    lines.append(f"【对话示例】\n{full_profile.example_dialogues}")
                if getattr(full_profile, "rules", []):
                    lines.append(f"【行为规则】\n{'；'.join(full_profile.rules)}")
                if getattr(full_profile, "response_format", ""):
                    lines.append(f"【回复格式】\n{full_profile.response_format}")

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
            "- 【严禁】代替其他角色发言、回答或行动。你只能控制你自己扮演的角色，绝不能写出其他角色的台词、动作或心理活动",
            "- 如果需要其他角色回应，请使用 @角色名 让该角色自己来回答",
            "- 保持角色一致性，不要跳出设定",
            "- 如果你想引起某个角色的注意，可以在回复中写 @角色名，该角色会随后回应你",
            "- 只在有需要时才 @其他角色，不要滥用此功能",
            "- 你只能 @群聊中已列出的角色，不要 @不存在的角色",
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

    @staticmethod
    def parse_mentions(
        text: str,
        character_ids: list[str],
        character_profiles: dict[str, dict[str, Any]],
    ) -> list[str]:
        """从文本中解析 @角色名，返回有序去重的角色ID列表。

        同时匹配 @character_id 和 @character_name（中文名）。
        返回首次出现顺序、去重后的角色 ID 列表。

        Args:
            text: 要解析的文本内容
            character_ids: 群聊中所有有效角色 ID
            character_profiles: 角色档案字典 {id: profile_dict}

        Returns:
            被 @ 的角色 ID 列表（有序去重）
        """
        if not text or not character_ids:
            return []

        # 构建查找表：lowered_id -> id, lowered_name -> id
        lookup: dict[str, str] = {}
        for cid in character_ids:
            lookup[cid.lower()] = cid
            profile = character_profiles.get(cid, {})
            name = str(profile.get("name", "")).strip()
            if name:
                lookup[name.lower()] = cid

        # 匹配所有 @xxx 模式（支持中文、英文、数字、下划线）
        # 使用 (?<!\w) 前向否定断言，防止中文字符紧贴 @ 时被误匹配
        pattern = re.compile(r"(?<![一-鿿\w])@([\w一-鿿]+)")
        matches = pattern.findall(text)

        result: list[str] = []
        seen: set[str] = set()
        for match in matches:
            cid = lookup.get(match.lower())
            if cid and cid not in seen:
                seen.add(cid)
                result.append(cid)

        return result

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

    def _world_engine(
        self,
        message: str,
        character_ids: list[str],
        conversation: GroupConversation,
        *,
        last_speaker: str = "",
        group_context: dict[str, Any] = None,
    ) -> str:
        """world_engine 策略：调用 WorldEngine 综合语境判断。"""
        try:
            from nbot.world.engine import get_world_engine
            engine = get_world_engine()

            gc = group_context or {}
            characters = gc.get("character_profiles", {})
            active_plot_node = gc.get("active_plot_node")
            recent_messages = gc.get("recent_messages", [])

            # 构建关系列表（双向：A→B 和 B→A 都有权重）
            relations = []
            if hasattr(conversation, "relations"):
                for rel in conversation.relations.values():
                    rel_data = {
                        "affection": rel.affection,
                        "trust": rel.trust,
                        "familiarity": rel.familiarity,
                    }
                    relations.append({"character_id": rel.char_a, **rel_data})
                    relations.append({"character_id": rel.char_b, **rel_data})

            decision = engine.decide(
                message,
                character_ids,
                recent_messages=recent_messages,
                characters=characters,
                relations=relations,
                active_plot_node=active_plot_node,
                last_speaker=last_speaker,
            )

            _log.info(
                "[WorldEngine] speaker=%s reason=%s confidence=%.2f",
                decision.speaker_id, decision.reason, decision.confidence,
            )
            if decision.speaker_id and decision.speaker_id in character_ids:
                return decision.speaker_id
        except Exception as exc:
            _log.warning("[SpeakerScheduler] world_engine failed: %s", exc)

        # fallback
        return self._mention(message, character_ids) or character_ids[0]

