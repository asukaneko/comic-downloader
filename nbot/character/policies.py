"""
Local user-signal analysis for the character runtime.

This module keeps the first-pass analysis fully local and deterministic:
keywords, tone markers, punctuation, softeners, current state, and
relationship context all contribute to a small set of normalized scores.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from nbot.character.models import CharacterState, RelationshipState

_log = logging.getLogger(__name__)


@dataclass
class UserSignals:
    """Normalized local interpretation of the user's current message."""

    praise_score: float = 0.0
    rejection_score: float = 0.0
    affection_score: float = 0.0
    hostility_score: float = 0.0
    care_score: float = 0.0
    intimacy_score: float = 0.0
    reassurance_score: float = 0.0
    vulnerability_score: float = 0.0
    question_score: float = 0.0
    command_score: float = 0.0
    sentiment_score: float = 0.0
    arousal_score: float = 0.0
    uncertainty_score: float = 0.0
    apology_score: float = 0.0
    playfulness_score: float = 0.0
    sadness_score: float = 0.0
    anger_score: float = 0.0
    anxiety_score: float = 0.0
    joy_score: float = 0.0
    fatigue_score: float = 0.0
    sarcasm_score: float = 0.0
    negation_scope_score: float = 0.0

    detected_keywords: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "praise_score": round(self.praise_score, 2),
            "rejection_score": round(self.rejection_score, 2),
            "affection_score": round(self.affection_score, 2),
            "hostility_score": round(self.hostility_score, 2),
            "care_score": round(self.care_score, 2),
            "intimacy_score": round(self.intimacy_score, 2),
            "reassurance_score": round(self.reassurance_score, 2),
            "vulnerability_score": round(self.vulnerability_score, 2),
            "question_score": round(self.question_score, 2),
            "command_score": round(self.command_score, 2),
            "sentiment_score": round(self.sentiment_score, 2),
            "arousal_score": round(self.arousal_score, 2),
            "uncertainty_score": round(self.uncertainty_score, 2),
            "apology_score": round(self.apology_score, 2),
            "playfulness_score": round(self.playfulness_score, 2),
            "sadness_score": round(self.sadness_score, 2),
            "anger_score": round(self.anger_score, 2),
            "anxiety_score": round(self.anxiety_score, 2),
            "joy_score": round(self.joy_score, 2),
            "fatigue_score": round(self.fatigue_score, 2),
            "sarcasm_score": round(self.sarcasm_score, 2),
            "negation_scope_score": round(self.negation_scope_score, 2),
            "detected_keywords": self.detected_keywords,
        }


_KEYWORD_RULES = {
    "praise": {
        "keywords": ["可爱", "好棒", "厉害", "优秀", "真好", "最棒", "最喜欢", "爱你", "真棒", "靠谱", "聪明", "懂我", "谢谢你", "感谢", "辛苦你了"],
        "score": 0.6,
    },
    "rejection": {
        "keywords": ["别烦", "讨厌", "走开", "滚", "不要你", "离我远点", "别管我", "别理我", "闭嘴", "烦死了"],
        "score": 0.7,
    },
    "affection": {
        "keywords": ["摸摸", "抱抱", "亲亲", "喜欢你", "想你", "爱你", "贴贴", "牵手", "在一起"],
        "score": 0.7,
    },
    "hostility": {
        "keywords": ["恨你", "去死", "废物", "垃圾", "蠢", "笨蛋", "恶心"],
        "score": 0.8,
    },
    "care": {
        "keywords": ["你还好吗", "辛苦了", "累不累", "注意休息", "别太累", "关心", "担心你", "照顾好自己"],
        "score": 0.5,
    },
    "intimacy": {
        "keywords": ["晚安", "早安", "想你了", "陪我", "一起", "永远", "一直", "不会离开"],
        "score": 0.5,
    },
    "reassurance": {
        "keywords": ["没事", "别怕", "我在", "不会离开", "我陪你", "别担心", "慢慢来", "没关系"],
        "score": 0.55,
    },
    "vulnerability": {
        "keywords": ["难过", "害怕", "委屈", "不安", "好累", "好难受", "心情不好", "没安全感"],
        "score": 0.45,
    },
}

_INTENSIFIERS = ["非常", "超级", "特别", "真的", "好", "太", "最", "超", "绝对"]
_DOWNTONERS = ["有点", "稍微", "可能", "也许", "大概", "一点", "好像"]
_SOFTENERS = ["请", "拜托", "可以吗", "好吗", "辛苦你", "麻烦你", "能不能"]
_APOLOGY_KEYWORDS = ["对不起", "抱歉", "不好意思", "我错了", "别生气", "原谅我"]
_UNCERTAINTY_KEYWORDS = ["吗", "呢", "是不是", "可以吗", "行不行", "能不能", "也许", "可能", "会不会"]
_PLAYFUL_KEYWORDS = ["哈哈", "嘿嘿", "hhh", "233", "逗你", "开玩笑", "略略", "哼哼", "笑死", "乐"]
_SADNESS_KEYWORDS = ["难过", "伤心", "想哭", "哭了", "崩溃", "失落", "委屈", "心酸", "撑不住", "没人懂"]
_ANGER_KEYWORDS = ["生气", "火大", "烦躁", "气死", "受不了", "离谱", "无语", "讨厌死", "真服了"]
_ANXIETY_KEYWORDS = ["焦虑", "紧张", "害怕", "慌", "不安", "担心", "怕", "怎么办", "完蛋", "糟了"]
_JOY_KEYWORDS = ["开心", "高兴", "快乐", "舒服", "安心", "期待", "喜欢", "太好了", "好耶"]
_FATIGUE_KEYWORDS = ["累", "困", "疲惫", "没力气", "不想动", "熬夜", "撑不住", "倦", "麻了"]
_NEGATION_MARKERS = ["不", "没", "没有", "别", "不是", "并不", "不太", "不要"]
_SARCASM_MARKERS = ["呵呵", "啊对对对", "真行", "可真", "你可真", "也是醉了", "笑死", "6", "行吧"]
_COMMAND_PATTERNS = ["帮我", "给我", "去做", "快点", "马上", "立刻", "现在就"]
_REST_CARE_KEYWORDS = ["休息", "睡觉", "补觉", "放松", "吃饭", "喝水", "别太累", "歇一会"]

_POSITIVE_FIELDS = (
    "praise_score",
    "affection_score",
    "care_score",
    "intimacy_score",
    "reassurance_score",
)
_NEGATIVE_FIELDS = ("rejection_score", "hostility_score")


def _clamp_score(value: float) -> float:
    return max(0.0, min(1.0, value))


def _contains_any(text: str, keywords: List[str]) -> List[str]:
    text_lower = text.lower()
    return [kw for kw in keywords if kw in text_lower]


def _boost_if(value: float, condition: bool, amount: float) -> float:
    if not condition:
        return value
    return _clamp_score(value + amount)


def _score_keywords(text: str, keywords: List[str], base: float = 0.22, per_hit: float = 0.12) -> float:
    hits = _contains_any(text, keywords)
    if not hits:
        return 0.0
    return _clamp_score(base + len(hits) * per_hit)


def _has_negated_keyword(text: str, keyword: str, window: int = 4) -> bool:
    for match in re.finditer(re.escape(keyword), text):
        prefix = text[max(0, match.start() - window):match.start()]
        if any(marker in prefix for marker in _NEGATION_MARKERS):
            return True
    return False


class SignalAnalyzer:
    """Analyze the current user message into local emotional/relational signals."""

    def analyze(
        self,
        user_message: str,
        state: Optional[CharacterState] = None,
        relationship: Optional[RelationshipState] = None,
    ) -> UserSignals:
        signals = UserSignals()
        if not user_message:
            return signals

        intensity_multiplier = 1.0
        matched_intensifiers = _contains_any(user_message, _INTENSIFIERS)
        matched_downtoners = _contains_any(user_message, _DOWNTONERS)
        matched_softeners = _contains_any(user_message, _SOFTENERS)

        if matched_intensifiers:
            intensity_multiplier += min(0.35, len(matched_intensifiers) * 0.08)
            signals.detected_keywords.extend(matched_intensifiers)
        if matched_downtoners:
            intensity_multiplier -= min(0.25, len(matched_downtoners) * 0.06)
            signals.detected_keywords.extend(matched_downtoners)
        if matched_softeners:
            signals.detected_keywords.extend(matched_softeners)

        for category, rule in _KEYWORD_RULES.items():
            matched = _contains_any(user_message, rule["keywords"])
            if not matched:
                continue

            score = _clamp_score((rule["score"] + len(matched) * 0.1) * intensity_multiplier)
            signals.detected_keywords.extend(matched)

            if category == "praise":
                signals.praise_score = score
            elif category == "rejection":
                signals.rejection_score = score
            elif category == "affection":
                signals.affection_score = score
            elif category == "hostility":
                signals.hostility_score = score
            elif category == "care":
                signals.care_score = score
            elif category == "intimacy":
                signals.intimacy_score = score
            elif category == "reassurance":
                signals.reassurance_score = score
            elif category == "vulnerability":
                signals.vulnerability_score = score

        question_marks = user_message.count("?") + user_message.count("？")
        if question_marks or "吗" in user_message or "呢" in user_message:
            signals.question_score = _clamp_score(
                0.25 + question_marks * 0.12 + (0.18 if ("吗" in user_message or "呢" in user_message) else 0.0)
            )

        matched_apologies = _contains_any(user_message, _APOLOGY_KEYWORDS)
        if matched_apologies:
            signals.apology_score = _clamp_score(0.45 + len(matched_apologies) * 0.12)
            signals.care_score = max(signals.care_score, signals.apology_score * 0.6)
            signals.detected_keywords.extend(matched_apologies)

        matched_uncertainty = _contains_any(user_message, _UNCERTAINTY_KEYWORDS)
        if matched_uncertainty or signals.question_score > 0:
            signals.uncertainty_score = _clamp_score(
                0.2 + len(matched_uncertainty) * 0.08 + signals.question_score * 0.35
            )
            signals.detected_keywords.extend(matched_uncertainty)

        matched_playful = _contains_any(user_message, _PLAYFUL_KEYWORDS)
        if matched_playful:
            signals.playfulness_score = _clamp_score(0.3 + len(matched_playful) * 0.14)
            signals.detected_keywords.extend(matched_playful)

        self._apply_affect_lexicons(signals, user_message, intensity_multiplier)

        command_hits = [pattern for pattern in _COMMAND_PATTERNS if pattern in user_message]
        if command_hits:
            raw_command = 0.35 + len(command_hits) * 0.12
            soften_ratio = min(0.25, len(matched_softeners) * 0.08)
            signals.command_score = _clamp_score(raw_command - soften_ratio)
            signals.detected_keywords.extend(command_hits)

        exclamation_count = user_message.count("!") + user_message.count("！")
        repeated_mark_count = (
            user_message.count("??")
            + user_message.count("？？")
            + user_message.count("!!")
            + user_message.count("！！")
        )
        signals.arousal_score = _clamp_score(
            max(
                signals.praise_score,
                signals.rejection_score,
                signals.affection_score,
                signals.hostility_score,
                signals.care_score,
                signals.intimacy_score,
                signals.reassurance_score,
                signals.vulnerability_score,
            )
            + min(0.25, exclamation_count * 0.05 + repeated_mark_count * 0.08)
        )

        self._apply_state_context(signals, user_message, state)
        self._apply_relationship_context(signals, relationship)
        self._soften_or_disambiguate(signals, user_message, matched_softeners)

        positive_score = max(getattr(signals, field_name) for field_name in _POSITIVE_FIELDS)
        positive_score = max(positive_score, signals.joy_score)
        negative_score = max(getattr(signals, field_name) for field_name in _NEGATIVE_FIELDS)
        negative_score = max(negative_score, signals.sadness_score * 0.75, signals.anxiety_score * 0.6, signals.anger_score * 0.85, signals.fatigue_score * 0.45)
        if signals.sarcasm_score > 0.3 and positive_score > negative_score:
            positive_score *= 0.75
            negative_score = max(negative_score, signals.sarcasm_score * 0.45)
        signals.sentiment_score = max(-1.0, min(1.0, positive_score - negative_score))

        return signals

    def _apply_affect_lexicons(self, signals: UserSignals, user_message: str, intensity_multiplier: float) -> None:
        groups = [
            ("sadness_score", _SADNESS_KEYWORDS),
            ("anger_score", _ANGER_KEYWORDS),
            ("anxiety_score", _ANXIETY_KEYWORDS),
            ("joy_score", _JOY_KEYWORDS),
            ("fatigue_score", _FATIGUE_KEYWORDS),
        ]
        for field_name, keywords in groups:
            hits = _contains_any(user_message, keywords)
            valid_hits = [kw for kw in hits if not _has_negated_keyword(user_message, kw)]
            if hits and len(valid_hits) < len(hits):
                signals.negation_scope_score = _clamp_score(signals.negation_scope_score + 0.12)
            if valid_hits:
                setattr(signals, field_name, _clamp_score((0.22 + len(valid_hits) * 0.13) * intensity_multiplier))
                signals.detected_keywords.extend(valid_hits)

        sarcasm_hits = _contains_any(user_message, _SARCASM_MARKERS)
        if sarcasm_hits:
            signals.sarcasm_score = _clamp_score(0.2 + len(sarcasm_hits) * 0.14)
            signals.detected_keywords.extend(sarcasm_hits)
            if signals.praise_score > 0 and signals.joy_score < 0.25:
                signals.praise_score *= 0.65
            signals.anger_score = _boost_if(signals.anger_score, True, 0.12)

        if signals.sadness_score > 0 or signals.anxiety_score > 0 or signals.fatigue_score > 0:
            signals.vulnerability_score = max(
                signals.vulnerability_score,
                _clamp_score(max(signals.sadness_score, signals.anxiety_score, signals.fatigue_score) * 0.85),
            )
        if signals.anger_score > 0 and signals.hostility_score == 0 and signals.rejection_score == 0:
            signals.rejection_score = max(signals.rejection_score, signals.anger_score * 0.45)
        if signals.joy_score > 0:
            signals.sentiment_score = max(signals.sentiment_score, signals.joy_score * 0.5)

    def _apply_state_context(
        self,
        signals: UserSignals,
        user_message: str,
        state: Optional[CharacterState],
    ) -> None:
        if not state:
            return

        if state.energy <= 35 and any(keyword in user_message for keyword in _REST_CARE_KEYWORDS):
            signals.care_score = _boost_if(signals.care_score, True, 0.24)
            signals.reassurance_score = _boost_if(signals.reassurance_score, True, 0.1)
            if signals.reassurance_score > 0:
                signals.care_score = _boost_if(signals.care_score, True, 0.18)

        if state.mood in {"受伤", "委屈", "不安"}:
            if signals.reassurance_score > 0:
                signals.reassurance_score = _boost_if(signals.reassurance_score, True, 0.12)
            if signals.care_score > 0:
                signals.care_score = _boost_if(signals.care_score, True, 0.1)
            elif signals.reassurance_score > 0:
                signals.care_score = _boost_if(signals.care_score, True, 0.28)

        if state.mood_intensity >= 0.75 and signals.command_score > 0:
            signals.command_score = _boost_if(signals.command_score, True, 0.08)

    def _apply_relationship_context(
        self,
        signals: UserSignals,
        relationship: Optional[RelationshipState],
    ) -> None:
        if not relationship:
            return

        if relationship.security < 30:
            if signals.rejection_score > 0:
                signals.rejection_score = _clamp_score(signals.rejection_score * 1.3)
            if signals.hostility_score > 0:
                signals.hostility_score = _clamp_score(signals.hostility_score * 1.2)
            if signals.reassurance_score > 0:
                signals.reassurance_score = _boost_if(signals.reassurance_score, True, 0.15)

        if relationship.trust > 70 and signals.apology_score > 0:
            signals.rejection_score *= 0.7
            signals.hostility_score *= 0.7

        if relationship.familiarity > 75 and signals.command_score > 0 and signals.care_score > 0:
            signals.command_score = max(0.0, signals.command_score - 0.12)

        if relationship.dependency > 70 and signals.reassurance_score > 0:
            signals.intimacy_score = _boost_if(signals.intimacy_score, True, 0.1)

    def _soften_or_disambiguate(
        self,
        signals: UserSignals,
        user_message: str,
        matched_softeners: List[str],
    ) -> None:
        if signals.playfulness_score > 0 and signals.hostility_score > 0:
            playful_factor = 0.35 if any(marker in user_message for marker in ("逗你", "开玩笑", "哈哈", "嘿嘿")) else 0.65
            signals.hostility_score *= playful_factor
            signals.rejection_score *= 0.6

        if matched_softeners and signals.command_score > 0:
            signals.command_score = max(0.0, signals.command_score - 0.08)

        if signals.vulnerability_score > 0 and signals.question_score > 0:
            signals.uncertainty_score = _boost_if(signals.uncertainty_score, True, 0.1)
        elif signals.vulnerability_score > 0:
            signals.uncertainty_score = _boost_if(signals.uncertainty_score, True, 0.05)

        if signals.reassurance_score > 0 and "不会离开" in user_message:
            signals.intimacy_score = _boost_if(signals.intimacy_score, True, 0.12)
