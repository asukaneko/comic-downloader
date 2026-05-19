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
    "reassurance": {
        "visible": "放松",
        "hidden": "被安抚后的依赖",
        "tone": "relieved_soft",
    },
    "vulnerability": {
        "visible": "心疼",
        "hidden": "想先接住对方的情绪",
        "tone": "gentle_supportive",
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
        }

        strongest = max(signal_scores, key=lambda key: signal_scores[key])
        strongest_score = signal_scores[strongest]

        if signals.vulnerability_score > 0.45 and signals.hostility_score < 0.35:
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
