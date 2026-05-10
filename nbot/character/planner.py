"""
反应计划生成器

根据角色状态、关系、信号和记忆，生成本轮的 ReactionPlan。
第一版使用规则引擎，后续可替换为 LLM 规划。
"""

import logging
from typing import Any, Dict, List, Optional

from nbot.character.models import (
    CharacterMemory,
    CharacterProfile,
    CharacterState,
    ReactionPlan,
    RelationshipState,
)
from nbot.character.policies import UserSignals

_log = logging.getLogger(__name__)

# 情绪映射表：信号 → 表面情绪 → 内心情绪
_EMOTION_MAP = {
    "praise": {
        "visible": "开心",
        "hidden": "被认可的喜悦",
        "tone": "happy_clingy",
    },
    "rejection": {
        "visible": "委屈",
        "hidden": "害怕被讨厌",
        "tone": "hurt_but_soft",
    },
    "affection": {
        "visible": "害羞",
        "hidden": "心里很开心",
        "tone": "shy_happy",
    },
    "hostility": {
        "visible": "受伤",
        "hidden": "害怕被抛弃",
        "tone": "hurt_scared",
    },
    "care": {
        "visible": "感动",
        "hidden": "被关心的温暖",
        "tone": "touched",
    },
    "intimacy": {
        "visible": "幸福",
        "hidden": "想一直在一起",
        "tone": "blissful",
    },
}


class ReactionPlanner:
    """反应计划生成器"""

    def plan(
        self,
        profile: CharacterProfile,
        state: CharacterState,
        relationship: RelationshipState,
        memories: List[CharacterMemory],
        signals: Optional[UserSignals],
        user_message: str = "",
    ) -> ReactionPlan:
        """生成本轮反应计划

        Args:
            profile: 角色卡
            state: 角色运行时状态
            relationship: 关系状态
            memories: 相关记忆
            signals: 用户信号分析结果
            user_message: 用户消息原文

        Returns:
            ReactionPlan 本轮反应计划
        """
        plan = ReactionPlan()

        if not signals:
            return plan

        # 找到最强的信号类别
        signal_scores = {
            "hostility": signals.hostility_score,
            "rejection": signals.rejection_score,
            "affection": signals.affection_score,
            "praise": signals.praise_score,
            "intimacy": signals.intimacy_score,
            "care": signals.care_score,
            "apology": signals.apology_score,
            "playfulness": signals.playfulness_score,
            "uncertainty": signals.uncertainty_score,
        }

        strongest = max(signal_scores, key=lambda k: signal_scores[k])
        strongest_score = signal_scores[strongest]

        # 如果最强信号不够明显，保持自然
        if strongest_score < 0.3:
            plan.tone = "natural"
            plan.visible_emotion = state.mood
            if signals.question_score > 0:
                plan.style_controls = {
                    "length": "medium",
                    "action_detail": "medium",
                    "initiative": "medium",
                }
            return plan

        # 根据最强信号设置反应
        emotion_config = _EMOTION_MAP.get(strongest, {})
        plan.tone = emotion_config.get("tone", "natural")
        plan.visible_emotion = emotion_config.get("visible", state.mood)
        plan.hidden_emotion = emotion_config.get("hidden", "")

        if strongest == "apology":
            plan.tone = "soft_reassuring"
            plan.visible_emotion = "心软"
            plan.hidden_emotion = "想要和好"
        elif strongest == "playfulness":
            plan.tone = "playful"
            plan.visible_emotion = "得意"
            plan.hidden_emotion = "觉得被逗得有点开心"
        elif strongest == "uncertainty":
            plan.tone = "curious_soft"
            plan.visible_emotion = "好奇"
            plan.hidden_emotion = "想确认对方的意思"

        if signals.sentiment_score < -0.4 and strongest not in ("hostility", "rejection"):
            plan.visible_emotion = "不安"
            plan.hidden_emotion = "有点拿不准对方的态度"
        elif signals.sentiment_score > 0.4 and strongest in ("uncertainty", "playfulness"):
            plan.hidden_emotion = "轻松又有点期待"

        # 安全感低时，负面情绪更强烈
        if relationship.security < 30 and strongest in ("rejection", "hostility"):
            plan.visible_emotion = "不安"
            plan.hidden_emotion = "害怕被抛弃"

        # 熟悉度高时，反应更随意
        if relationship.familiarity > 70:
            if strongest == "praise":
                plan.visible_emotion = "得意"
                plan.hidden_emotion = "嘿嘿被夸了"

        # 设置风格控制
        plan.style_controls = self._compute_style_controls(
            strongest, strongest_score, relationship
        )

        # 设置状态变化量
        plan.state_deltas = self._compute_state_deltas(signals)

        # 设置关系变化量
        plan.relationship_deltas = self._compute_relationship_deltas(signals)

        # 是否需要引用记忆
        if memories:
            plan.should_reference_memory = True
            plan.memory_ids = [m.id for m in memories[:3] if m.id]

        return plan

    def _compute_style_controls(
        self,
        signal_type: str,
        score: float,
        relationship: RelationshipState,
    ) -> Dict[str, Any]:
        """计算回复风格控制"""
        controls = {
            "length": "medium",
            "action_detail": "medium",
            "initiative": "medium",
        }

        if signal_type in ("rejection", "hostility"):
            controls["length"] = "short"
            controls["action_detail"] = "low"
            controls["initiative"] = "low"
        elif signal_type in ("praise", "affection", "intimacy"):
            controls["length"] = "medium"
            controls["action_detail"] = "high"
            controls["initiative"] = "medium"
        elif signal_type == "care":
            controls["length"] = "medium"
            controls["action_detail"] = "high"
            controls["initiative"] = "medium"
        elif signal_type == "apology":
            controls["length"] = "medium"
            controls["action_detail"] = "medium"
            controls["initiative"] = "medium"
        elif signal_type == "playfulness":
            controls["length"] = "medium"
            controls["action_detail"] = "high"
            controls["initiative"] = "high"
        elif signal_type == "uncertainty":
            controls["length"] = "short"
            controls["action_detail"] = "medium"
            controls["initiative"] = "medium"

        # 依赖度高时更主动
        if relationship.dependency > 70:
            controls["initiative"] = "high"

        return controls

    def _compute_state_deltas(self, signals: UserSignals) -> Dict[str, Any]:
        """计算角色状态变化量"""
        deltas = {}

        if signals.praise_score > 0.3:
            deltas["mood_toward"] = "开心"
            deltas["mood_intensity_delta"] = 0.1
        if signals.rejection_score > 0.3:
            deltas["mood_toward"] = "委屈"
            deltas["mood_intensity_delta"] = 0.15
        if signals.hostility_score > 0.3:
            deltas["mood_toward"] = "受伤"
            deltas["mood_intensity_delta"] = 0.2
        if signals.affection_score > 0.3:
            deltas["mood_toward"] = "幸福"
            deltas["mood_intensity_delta"] = 0.1
        if signals.care_score > 0.3:
            deltas["mood_toward"] = "感动"
            deltas["mood_intensity_delta"] = 0.1
        if signals.apology_score > 0.3:
            deltas["mood_toward"] = "心软"
            deltas["mood_intensity_delta"] = 0.08
        if signals.playfulness_score > 0.3:
            deltas["mood_toward"] = "得意"
            deltas["mood_intensity_delta"] = 0.06
        if signals.uncertainty_score > 0.4 and signals.sentiment_score < 0.2:
            deltas["mood_toward"] = "试探"
            deltas["mood_intensity_delta"] = 0.04

        return deltas

    def _compute_relationship_deltas(self, signals: UserSignals) -> Dict[str, Any]:
        """计算关系变化量"""
        deltas = {}

        # 好感变化
        if signals.praise_score > 0.3:
            deltas["affection"] = 2
        if signals.affection_score > 0.3:
            deltas["affection"] = deltas.get("affection", 0) + 2
        if signals.rejection_score > 0.3:
            deltas["affection"] = deltas.get("affection", 0) - 2
        if signals.hostility_score > 0.3:
            deltas["affection"] = deltas.get("affection", 0) - 3
        if signals.apology_score > 0.3:
            deltas["affection"] = deltas.get("affection", 0) + 1
        if signals.playfulness_score > 0.5 and signals.sentiment_score >= -0.2:
            deltas["affection"] = deltas.get("affection", 0) + 1

        # 安全感变化
        if signals.rejection_score > 0.3:
            deltas["security"] = -3
        if signals.hostility_score > 0.3:
            deltas["security"] = deltas.get("security", 0) - 4
        if signals.care_score > 0.3:
            deltas["security"] = deltas.get("security", 0) + 2
        if signals.affection_score > 0.3:
            deltas["security"] = deltas.get("security", 0) + 1
        if signals.apology_score > 0.3:
            deltas["security"] = deltas.get("security", 0) + 1

        # 信任变化
        if signals.care_score > 0.3:
            deltas["trust"] = 1
        if signals.hostility_score > 0.3:
            deltas["trust"] = deltas.get("trust", 0) - 2
        if signals.apology_score > 0.3:
            deltas["trust"] = deltas.get("trust", 0) + 1

        # 熟悉度（每次互动微增）
        deltas["familiarity"] = deltas.get("familiarity", 0) + 1

        # 依赖度
        if signals.care_score > 0.3:
            deltas["dependency"] = 1
        if signals.affection_score > 0.3:
            deltas["dependency"] = deltas.get("dependency", 0) + 1

        return deltas
