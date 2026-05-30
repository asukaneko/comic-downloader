"""
Local reaction planner for the character runtime.

The planner turns the current state, relationship, signals, and memories
into a turn-level ReactionPlan that can be injected into prompting and used
by the local state machine.
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

_EMOTION_MAP = {
    # ── 正面情感 ──
    "praise": {
        "visible": "开心",
        "hidden": "被认可的喜悦",
        "tone": "happy_clingy",
    },
    "affection": {
        "visible": "害羞",
        "hidden": "心里很开心",
        "tone": "shy_happy",
    },
    "intimacy": {
        "visible": "幸福",
        "hidden": "想一直在一起",
        "tone": "blissful",
    },
    "care": {
        "visible": "感动",
        "hidden": "被关心的温暖",
        "tone": "touched",
    },
    "reassurance": {
        "visible": "放松",
        "hidden": "被安抚后的依赖",
        "tone": "relieved_soft",
    },
    "joy": {
        "visible": "开心",
        "hidden": "被对方情绪感染得轻快",
        "tone": "bright_warm",
    },
    "playfulness": {
        "visible": "得意",
        "hidden": "觉得被逗得有点开心",
        "tone": "playful",
    },

    # ── 负面情感 ──
    "rejection": {
        "visible": "委屈",
        "hidden": "害怕被讨厌",
        "tone": "hurt_but_soft",
    },
    "hostility": {
        "visible": "受伤",
        "hidden": "害怕被抛弃",
        "tone": "hurt_scared",
    },
    "sadness": {
        "visible": "心疼",
        "hidden": "想靠近并安抚对方",
        "tone": "gentle_supportive",
    },
    "anger": {
        "visible": "谨慎",
        "hidden": "想先稳住气氛",
        "tone": "calm_careful",
    },
    "anxiety": {
        "visible": "担心",
        "hidden": "想让对方安心一点",
        "tone": "steady_reassuring",
    },
    "fatigue": {
        "visible": "心疼",
        "hidden": "想让对方先休息",
        "tone": "soft_caring",
    },

    # ── 复合/微妙情感 ──
    "vulnerability": {
        "visible": "心疼",
        "hidden": "想先接住对方的情绪",
        "tone": "gentle_supportive",
    },
    "apology": {
        "visible": "心软",
        "hidden": "想要和好",
        "tone": "soft_reassuring",
    },
    "uncertainty": {
        "visible": "好奇",
        "hidden": "想确认对方的意思",
        "tone": "curious_soft",
    },
    "sarcasm": {
        "visible": "无奈",
        "hidden": "不知道该生气还是该笑",
        "tone": "teasing_resigned",
    },
    "command": {
        "visible": "乖巧",
        "hidden": "有点紧张但愿意听从",
        "tone": "obedient_soft",
    },
    "arousal": {
        "visible": "羞涩",
        "hidden": "心跳加速但不想表现出来",
        "tone": "flustered_aware",
    },
    "negation_scope": {
        "visible": "困惑",
        "hidden": "在努力理解对方的意思",
        "tone": "confused_gentle",
    },

    # ── 场景化情感 ──
    "teasing": {
        "visible": "嗔怪",
        "hidden": "其实觉得有点甜",
        "tone": "tsundere_soft",
    },
    "longing": {
        "visible": "落寞",
        "hidden": "很想靠近又怕打扰",
        "tone": "quiet_yearning",
    },
    "jealousy": {
        "visible": "冷淡",
        "hidden": "在意得不行但不想承认",
        "tone": "cold_pouty",
    },
    "gratitude": {
        "visible": "感动",
        "hidden": "不知道怎么回报才好",
        "tone": "warm_overwhelmed",
    },
    "embarrassment": {
        "visible": "慌张",
        "hidden": "想找个地方躲起来",
        "tone": "flustered_shy",
    },
    "surprise": {
        "visible": "惊讶",
        "hidden": "没想到会这样",
        "tone": "startled_warm",
    },
    "disappointment": {
        "visible": "沉默",
        "hidden": "有点难过但不想说出来",
        "tone": "quiet_hurt",
    },
    "nostalgia": {
        "visible": "恍惚",
        "hidden": "想起了以前的事",
        "tone": "wistful_tender",
    },
    "determination": {
        "visible": "认真",
        "hidden": "想为对方变得更好",
        "tone": "earnest_warm",
    },
    "helplessness": {
        "visible": "无奈",
        "hidden": "想帮忙但不知道怎么做",
        "tone": "gentle_lost",
    },
}


class ReactionPlanner:
    """Generate a local turn-level reaction plan."""

    def plan(
        self,
        profile: CharacterProfile,
        state: CharacterState,
        relationship: RelationshipState,
        memories: List[CharacterMemory],
        signals: Optional[UserSignals],
        user_message: str = "",
    ) -> ReactionPlan:
        plan = ReactionPlan()

        if not signals:
            return plan

        signal_scores = {
            "hostility": signals.hostility_score,
            "rejection": signals.rejection_score,
            "affection": signals.affection_score,
            "praise": signals.praise_score,
            "intimacy": signals.intimacy_score,
            "care": signals.care_score,
            "reassurance": signals.reassurance_score,
            "vulnerability": signals.vulnerability_score,
            "apology": signals.apology_score,
            "playfulness": signals.playfulness_score,
            "uncertainty": signals.uncertainty_score,
            "sadness": signals.sadness_score,
            "anger": signals.anger_score,
            "anxiety": signals.anxiety_score,
            "joy": signals.joy_score,
            "fatigue": signals.fatigue_score,
            "sarcasm": signals.sarcasm_score,
            "command": signals.command_score,
            "arousal": signals.arousal_score,
        }

        strongest = max(signal_scores, key=lambda key: signal_scores[key])
        strongest_score = signal_scores[strongest]

        if signals.fatigue_score > 0.45 and signals.hostility_score < 0.35:
            strongest = "fatigue"
            strongest_score = signals.fatigue_score
        elif signals.sadness_score > 0.45 and signals.hostility_score < 0.35:
            strongest = "sadness"
            strongest_score = signals.sadness_score
        elif signals.anxiety_score > 0.45 and signals.hostility_score < 0.35:
            strongest = "anxiety"
            strongest_score = signals.anxiety_score
        elif signals.vulnerability_score > 0.45 and signals.hostility_score < 0.35:
            strongest = "vulnerability"
            strongest_score = signals.vulnerability_score
        elif signals.reassurance_score > 0.5 and relationship.security < 45:
            strongest = "reassurance"
            strongest_score = signals.reassurance_score

        if strongest_score < 0.3:
            plan.intent = "respond_naturally"
            plan.tone = "natural"
            plan.visible_emotion = state.mood
            if signals.question_score > 0:
                plan.style_controls = {
                    "length": "medium",
                    "action_detail": "medium",
                    "initiative": "medium",
                }
            return plan

        emotion_config = _EMOTION_MAP.get(strongest, {})
        plan.tone = emotion_config.get("tone", "natural")
        plan.visible_emotion = emotion_config.get("visible", state.mood)
        plan.hidden_emotion = emotion_config.get("hidden", "")
        plan.intent = self._compute_intent(strongest, signals)

        if signals.sentiment_score < -0.4 and strongest not in ("hostility", "rejection"):
            plan.visible_emotion = "不安"
            plan.hidden_emotion = "有点拿不准对方的态度"
        elif signals.sentiment_score > 0.4 and strongest in ("uncertainty", "playfulness"):
            plan.hidden_emotion = "轻松又有点期待"

        if signals.vulnerability_score > 0.45 and strongest not in ("hostility", "rejection"):
            plan.visible_emotion = "心疼"
            plan.hidden_emotion = "想先安抚对方"
            plan.tone = "gentle_supportive"
            if strongest in ("uncertainty", "reassurance"):
                plan.intent = "comfort_and_stabilize"

        if signals.reassurance_score > 0.45 and relationship.security < 45:
            plan.visible_emotion = "放松"
            plan.hidden_emotion = "终于有一点安心"
            plan.tone = "relieved_soft"

        if relationship.security < 30 and strongest in ("rejection", "hostility"):
            plan.visible_emotion = "不安"
            plan.hidden_emotion = "害怕被抛弃"

        if relationship.familiarity > 70 and strongest == "praise":
            plan.visible_emotion = "得意"
            plan.hidden_emotion = "被夸之后更想贴近对方"

        plan.style_controls = self._compute_style_controls(strongest, relationship, signals)
        plan.state_deltas = self._compute_state_deltas(signals)
        plan.relationship_deltas = self._compute_relationship_deltas(signals)

        if memories:
            plan.should_reference_memory = True
            plan.memory_ids = [memory.id for memory in memories[:3] if memory.id]

        return plan

    def _compute_intent(self, signal_type: str, signals: UserSignals) -> str:
        intent_map = {
            "hostility": "show_hurt_and_pull_back",
            "rejection": "seek_reassurance_gently",
            "affection": "reciprocate_affection",
            "praise": "receive_praise_and_move_closer",
            "intimacy": "deepen_closeness",
            "care": "soften_and_receive_care",
            "reassurance": "accept_reassurance_and_soften",
            "vulnerability": "comfort_and_stabilize",
            "apology": "repair_relationship",
            "playfulness": "play_back",
            "uncertainty": "gently_probe_and_clarify",
            "sadness": "comfort_and_stabilize",
            "anger": "deescalate_and_validate",
            "anxiety": "reassure_and_ground",
            "joy": "share_positive_emotion",
            "fatigue": "encourage_rest_gently",
        }
        intent = intent_map.get(signal_type, "respond_naturally")
        if signal_type == "uncertainty" and signals.sentiment_score < -0.2:
            return "clarify_cautiously"
        return intent

    def _compute_style_controls(
        self,
        signal_type: str,
        relationship: RelationshipState,
        signals: UserSignals,
    ) -> Dict[str, Any]:
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
            controls["action_detail"] = "high"
        elif signal_type == "care":
            controls["action_detail"] = "high"
        elif signal_type == "reassurance":
            controls["action_detail"] = "medium"
        elif signal_type == "vulnerability":
            controls["initiative"] = "low"
        elif signal_type == "playfulness":
            controls["action_detail"] = "high"
            controls["initiative"] = "high"
        elif signal_type == "uncertainty":
            controls["length"] = "short"
        elif signal_type in ("sadness", "anxiety", "fatigue"):
            controls["initiative"] = "low"
            controls["action_detail"] = "medium"
        elif signal_type == "anger":
            controls["length"] = "short"
            controls["action_detail"] = "low"
            controls["initiative"] = "low"
        elif signal_type == "joy":
            controls["action_detail"] = "high"

        if relationship.dependency > 70:
            controls["initiative"] = "high"
        if signals.vulnerability_score > 0.45 and signals.hostility_score < 0.35:
            controls["length"] = "medium"
            controls["initiative"] = "low"
        if signals.question_score > 0.5 and signal_type not in ("hostility", "rejection"):
            controls["length"] = "medium"

        return controls

    def _compute_state_deltas(self, signals: UserSignals) -> Dict[str, Any]:
        deltas: Dict[str, Any] = {}

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
        if signals.reassurance_score > 0.35:
            deltas["mood_toward"] = "放松"
            deltas["mood_intensity_delta"] = 0.08
        if signals.apology_score > 0.3:
            deltas["mood_toward"] = "心软"
            deltas["mood_intensity_delta"] = 0.08
        if signals.playfulness_score > 0.3:
            deltas["mood_toward"] = "得意"
            deltas["mood_intensity_delta"] = 0.06
        if signals.uncertainty_score > 0.4 and signals.sentiment_score < 0.2:
            deltas["mood_toward"] = "试探"
            deltas["mood_intensity_delta"] = 0.04
        if signals.vulnerability_score > 0.45 and signals.hostility_score < 0.35:
            deltas["mood_toward"] = "心疼"
            deltas["mood_intensity_delta"] = 0.1
        if signals.sadness_score > 0.4 and signals.hostility_score < 0.35:
            deltas["mood_toward"] = "心疼"
            deltas["mood_intensity_delta"] = 0.12
        if signals.anxiety_score > 0.4 and signals.hostility_score < 0.35:
            deltas["mood_toward"] = "担心"
            deltas["mood_intensity_delta"] = 0.1
        if signals.fatigue_score > 0.4:
            deltas["mood_toward"] = "心疼"
            deltas["mood_intensity_delta"] = 0.08
        if signals.anger_score > 0.45 and signals.hostility_score < 0.35:
            deltas["mood_toward"] = "谨慎"
            deltas["mood_intensity_delta"] = 0.08
        if signals.joy_score > 0.45 and signals.sentiment_score > 0:
            deltas["mood_toward"] = "开心"
            deltas["mood_intensity_delta"] = 0.08

        return deltas

    def _compute_relationship_deltas(self, signals: UserSignals) -> Dict[str, Any]:
        deltas: Dict[str, Any] = {}

        if signals.praise_score > 0.3:
            deltas["affection"] = 2
        if signals.affection_score > 0.3:
            deltas["affection"] = deltas.get("affection", 0) + 2
        if signals.reassurance_score > 0.35:
            deltas["affection"] = deltas.get("affection", 0) + 1
        if signals.rejection_score > 0.3:
            deltas["affection"] = deltas.get("affection", 0) - 2
        if signals.hostility_score > 0.3:
            deltas["affection"] = deltas.get("affection", 0) - 3
        if signals.apology_score > 0.3:
            deltas["affection"] = deltas.get("affection", 0) + 1
        if signals.playfulness_score > 0.5 and signals.sentiment_score >= -0.2:
            deltas["affection"] = deltas.get("affection", 0) + 1

        if signals.rejection_score > 0.3:
            deltas["security"] = -3
        if signals.hostility_score > 0.3:
            deltas["security"] = deltas.get("security", 0) - 4
        if signals.care_score > 0.3:
            deltas["security"] = deltas.get("security", 0) + 2
        if signals.affection_score > 0.3:
            deltas["security"] = deltas.get("security", 0) + 1
        if signals.reassurance_score > 0.35:
            deltas["security"] = deltas.get("security", 0) + 2
        if signals.apology_score > 0.3:
            deltas["security"] = deltas.get("security", 0) + 1

        if signals.care_score > 0.3:
            deltas["trust"] = 1
        if signals.reassurance_score > 0.35:
            deltas["trust"] = deltas.get("trust", 0) + 1
        if signals.hostility_score > 0.3:
            deltas["trust"] = deltas.get("trust", 0) - 2
        if signals.apology_score > 0.3:
            deltas["trust"] = deltas.get("trust", 0) + 1

        deltas["familiarity"] = deltas.get("familiarity", 0) + 1

        if signals.care_score > 0.3:
            deltas["dependency"] = 1
        if signals.affection_score > 0.3:
            deltas["dependency"] = deltas.get("dependency", 0) + 1
        if signals.vulnerability_score > 0.45 and signals.care_score < 0.25:
            deltas["dependency"] = deltas.get("dependency", 0) - 1

        return deltas
