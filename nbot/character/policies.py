"""
信号分析器

分析用户输入中的情绪信号，为 ReactionPlanner 和 StateMachine 提供输入。
第一版使用关键词规则，后续可替换为 LLM 分析。
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from nbot.character.models import CharacterState, RelationshipState

_log = logging.getLogger(__name__)


@dataclass
class UserSignals:
    """用户输入信号分析结果"""

    praise_score: float = 0.0
    rejection_score: float = 0.0
    affection_score: float = 0.0
    hostility_score: float = 0.0
    care_score: float = 0.0
    intimacy_score: float = 0.0
    question_score: float = 0.0
    command_score: float = 0.0
    sentiment_score: float = 0.0
    arousal_score: float = 0.0
    uncertainty_score: float = 0.0
    apology_score: float = 0.0
    playfulness_score: float = 0.0

    detected_keywords: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "praise_score": round(self.praise_score, 2),
            "rejection_score": round(self.rejection_score, 2),
            "affection_score": round(self.affection_score, 2),
            "hostility_score": round(self.hostility_score, 2),
            "care_score": round(self.care_score, 2),
            "intimacy_score": round(self.intimacy_score, 2),
            "question_score": round(self.question_score, 2),
            "command_score": round(self.command_score, 2),
            "sentiment_score": round(self.sentiment_score, 2),
            "arousal_score": round(self.arousal_score, 2),
            "uncertainty_score": round(self.uncertainty_score, 2),
            "apology_score": round(self.apology_score, 2),
            "playfulness_score": round(self.playfulness_score, 2),
            "detected_keywords": self.detected_keywords,
        }


# 关键词规则表
_KEYWORD_RULES = {
    "praise": {
        "keywords": ["可爱", "好棒", "厉害", "优秀", "真好", "最棒", "最喜欢", "爱你", "厉害了", "好厉害", "真棒", "棒"],
        "score": 0.6,
    },
    "rejection": {
        "keywords": ["别烦", "讨厌", "走开", "滚", "不要你", "离我远点", "别管我", "别理我", "闭嘴", "烦死了"],
        "score": 0.7,
    },
    "affection": {
        "keywords": ["摸摸", "抱抱", "亲亲", "喜欢你", "想你", "爱你", "贴贴", "蹭蹭", "牵手", "在一起"],
        "score": 0.7,
    },
    "hostility": {
        "keywords": ["恨你", "去死", "废物", "垃圾", "蠢", "笨蛋", "丑", "恶心"],
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
}

_INTENSIFIERS = ["非常", "超级", "特别", "真的", "好", "太", "最", "超", "巨", "绝对"]
_DOWNTONERS = ["有点", "稍微", "可能", "也许", "大概", "一点"]
_APOLOGY_KEYWORDS = ["对不起", "抱歉", "不好意思", "我错了", "别生气", "原谅我"]
_UNCERTAINTY_KEYWORDS = ["吗", "嘛", "是不是", "可以吗", "行不行", "能不能", "也许", "可能"]
_PLAYFUL_KEYWORDS = ["嘿嘿", "哈哈", "嘻嘻", "笨蛋", "呆瓜", "逗你", "开玩笑", "略略"]
_POSITIVE_CATEGORIES = ("praise", "affection", "care", "intimacy")
_NEGATIVE_CATEGORIES = ("rejection", "hostility")


def _clamp_score(value: float) -> float:
    return max(0.0, min(1.0, value))


def _contains_any(text: str, keywords: List[str]) -> List[str]:
    """检查文本中是否包含关键词，返回匹配到的关键词列表"""
    text_lower = text.lower()
    return [kw for kw in keywords if kw in text_lower]


class SignalAnalyzer:
    """用户输入信号分析器"""

    def analyze(
        self,
        user_message: str,
        state: Optional[CharacterState] = None,
        relationship: Optional[RelationshipState] = None,
    ) -> UserSignals:
        """分析用户输入中的情绪信号

        Args:
            user_message: 用户消息文本
            state: 角色当前状态
            relationship: 关系状态

        Returns:
            UserSignals 分析结果
        """
        signals = UserSignals()
        if not user_message:
            return signals

        # 关键词匹配
        intensity_multiplier = 1.0
        matched_intensifiers = _contains_any(user_message, _INTENSIFIERS)
        matched_downtoners = _contains_any(user_message, _DOWNTONERS)
        if matched_intensifiers:
            intensity_multiplier += min(0.35, len(matched_intensifiers) * 0.08)
            signals.detected_keywords.extend(matched_intensifiers)
        if matched_downtoners:
            intensity_multiplier -= min(0.25, len(matched_downtoners) * 0.06)
            signals.detected_keywords.extend(matched_downtoners)

        for category, rule in _KEYWORD_RULES.items():
            matched = _contains_any(user_message, rule["keywords"])
            if matched:
                score = rule["score"]
                # 多个关键词叠加，但上限为 1.0
                adjusted = _clamp_score((score + len(matched) * 0.1) * intensity_multiplier)
                signals.detected_keywords.extend(matched)

                if category == "praise":
                    signals.praise_score = adjusted
                elif category == "rejection":
                    signals.rejection_score = adjusted
                elif category == "affection":
                    signals.affection_score = adjusted
                elif category == "hostility":
                    signals.hostility_score = adjusted
                elif category == "care":
                    signals.care_score = adjusted
                elif category == "intimacy":
                    signals.intimacy_score = adjusted

        # 问号检测
        if "？" in user_message or "?" in user_message:
            signals.question_score = 0.5

        matched_apologies = _contains_any(user_message, _APOLOGY_KEYWORDS)
        if matched_apologies:
            signals.apology_score = _clamp_score(0.45 + len(matched_apologies) * 0.12)
            signals.care_score = max(signals.care_score, signals.apology_score * 0.6)
            signals.detected_keywords.extend(matched_apologies)

        matched_uncertainty = _contains_any(user_message, _UNCERTAINTY_KEYWORDS)
        if matched_uncertainty or signals.question_score > 0:
            signals.uncertainty_score = _clamp_score(0.25 + len(matched_uncertainty) * 0.08)
            signals.detected_keywords.extend(matched_uncertainty)

        matched_playful = _contains_any(user_message, _PLAYFUL_KEYWORDS)
        if matched_playful:
            signals.playfulness_score = _clamp_score(0.35 + len(matched_playful) * 0.12)
            signals.detected_keywords.extend(matched_playful)

        # 命令式检测
        command_patterns = ["帮我", "给我", "去做", "快点", "马上"]
        if any(p in user_message for p in command_patterns):
            signals.command_score = 0.4

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
            )
            + min(0.25, exclamation_count * 0.05 + repeated_mark_count * 0.08)
        )

        positive_score = max(getattr(signals, f"{category}_score") for category in _POSITIVE_CATEGORIES)
        negative_score = max(getattr(signals, f"{category}_score") for category in _NEGATIVE_CATEGORIES)
        signals.sentiment_score = max(-1.0, min(1.0, positive_score - negative_score))

        if signals.playfulness_score > 0 and signals.hostility_score > 0:
            signals.hostility_score *= 0.65
            signals.rejection_score *= 0.75
            signals.sentiment_score = max(signals.sentiment_score, -0.2)

        # 关系状态修正：安全感低时，更容易感到不安
        if relationship and relationship.security < 30:
            if signals.rejection_score > 0:
                signals.rejection_score = min(signals.rejection_score * 1.3, 1.0)
            if signals.hostility_score > 0:
                signals.hostility_score = min(signals.hostility_score * 1.2, 1.0)

        if relationship and relationship.trust > 70 and signals.apology_score > 0:
            signals.rejection_score *= 0.7
            signals.hostility_score *= 0.7

        return signals
