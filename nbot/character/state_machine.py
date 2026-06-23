"""
状态机

负责根据信号和反应计划更新角色状态和关系状态。
核心原则：
- 情绪惯性：情绪不会一句话突变
- 数值边界：所有关系值在 0-100 范围内
- 每轮变化限幅：避免暴涨暴跌
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from nbot.character.models import (
    CharacterState,
    ReactionPlan,
    RelationshipState,
)
from nbot.character.policies import UserSignals

_log = logging.getLogger(__name__)

# 情绪惯性系数：旧情绪权重 0.75，新信号权重 0.25
_MOOD_INERTIA = 0.75

# 每轮变化限幅
_MAX_DELTA_PER_TURN = {
    "affection": 3,
    "trust": 3,
    "familiarity": 2,
    "dependency": 2,
    "security": 4,
    "jealousy": 2,
}

# 情绪转移表：定义情绪的自然变化路径
_MOOD_TRANSITIONS = {
    "开心": ["放松", "得意", "黏人"],
    "委屈": ["不安", "沉默", "伤心"],
    "害羞": ["开心", "放松"],
    "受伤": ["不安", "沉默", "委屈"],
    "感动": ["幸福", "依赖"],
    "幸福": ["黏人", "放松"],
    "不安": ["害怕", "试探"],
    "平静": ["放松", "期待"],
    "生气": ["沉默", "委屈"],
}

_RESTORATIVE_KEYWORDS = (
    "休息",
    "睡觉",
    "补觉",
    "放松",
    "歇一会",
    "休息一下",
    "吃饭",
    "喝水",
    "充电",
    "摸摸",
    "抱抱",
    "晚安",
)


def _clamp_energy(value: int) -> int:
    return max(0, min(100, int(value)))


def _signal_score(signals: Optional[UserSignals], field_name: str) -> float:
    if not signals:
        return 0.0
    try:
        return float(getattr(signals, field_name, 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


class StateMachine:
    """角色状态机，负责情绪和关系的更新"""

    def apply(
        self,
        old_state: CharacterState,
        old_relationship: RelationshipState,
        signals: Optional[UserSignals],
        plan: ReactionPlan,
        user_message: str = "",
        assistant_message: str = "",
    ) -> Tuple[CharacterState, RelationshipState]:
        """应用状态变化

        Args:
            old_state: 旧角色状态
            old_relationship: 旧关系状态
            signals: 用户信号
            plan: 反应计划
            user_message: 用户消息
            assistant_message: 助手回复

        Returns:
            (new_state, new_relationship) 元组
        """
        new_state = self._apply_state(
            old_state,
            plan,
            signals=signals,
            user_message=user_message,
            assistant_message=assistant_message,
        )
        new_relationship = self._apply_relationship(old_relationship, plan)
        return new_state, new_relationship

    def _apply_state(
        self,
        old_state: CharacterState,
        plan: ReactionPlan,
        signals: Optional[UserSignals] = None,
        user_message: str = "",
        assistant_message: str = "",
    ) -> CharacterState:
        """更新角色运行时状态"""
        new_state = CharacterState(
            character_id=old_state.character_id,
            scope_id=old_state.scope_id,
            mood=old_state.mood,
            mood_intensity=old_state.mood_intensity,
            energy=old_state.energy,
            scene=dict(old_state.scene),
            last_active_at=datetime.now().astimezone().isoformat(),
            updated_at=datetime.now().astimezone().isoformat(),
        )

        # 情绪更新
        deltas = plan.state_deltas
        if deltas:
            target_mood = deltas.get("mood_toward", old_state.mood)
            intensity_delta = deltas.get("mood_intensity_delta", 0.0)

            if target_mood != old_state.mood and (
                abs(intensity_delta) >= 0.08 or old_state.mood_intensity < 0.55
            ):
                # 情绪惯性：弱信号不会立刻覆盖较强的当前情绪
                new_state.mood = target_mood

            # 情绪强度更新：惯性混合
            new_intensity = (
                old_state.mood_intensity * _MOOD_INERTIA
                + (old_state.mood_intensity + intensity_delta) * (1 - _MOOD_INERTIA)
            )
            new_state.mood_intensity = max(0.0, min(1.0, new_intensity))
        else:
            # 无显著信号时缓慢回落，避免情绪长时间卡在高强度。
            new_state.mood_intensity = max(0.0, old_state.mood_intensity - 0.03)

        energy_delta = self._calculate_energy_delta(
            old_energy=old_state.energy,
            signals=signals,
            user_message=user_message,
            assistant_message=assistant_message,
        )
        new_state.energy = _clamp_energy(old_state.energy + energy_delta)

        return new_state

    def _calculate_energy_delta(
        self,
        *,
        old_energy: int,
        signals: Optional[UserSignals],
        user_message: str,
        assistant_message: str,
    ) -> int:
        """Return the local per-turn energy change before the 6-turn AI evaluator."""
        delta = 0

        if old_energy < 30:
            delta += 2
        elif old_energy < 65:
            delta += 1

        care = _signal_score(signals, "care_score")
        affection = _signal_score(signals, "affection_score")
        intimacy = _signal_score(signals, "intimacy_score")
        praise = _signal_score(signals, "praise_score")
        apology = _signal_score(signals, "apology_score")
        playfulness = _signal_score(signals, "playfulness_score")
        hostility = _signal_score(signals, "hostility_score")
        rejection = _signal_score(signals, "rejection_score")
        command = _signal_score(signals, "command_score")
        arousal = _signal_score(signals, "arousal_score")

        if care >= 0.45:
            delta += 2
        if max(affection, intimacy, praise) >= 0.65:
            delta += 1
        if apology >= 0.45:
            delta += 1
        if playfulness >= 0.35 and hostility < 0.4:
            delta += 1

        lowered_message = (user_message or "").lower()
        has_restorative_keyword = any(
            keyword in lowered_message for keyword in _RESTORATIVE_KEYWORDS
        )
        if has_restorative_keyword:
            delta += 2

        if max(hostility, rejection) >= 0.6:
            delta -= 2
        if command >= 0.4:
            delta -= 1
        if arousal >= 0.75 and care < 0.45:
            delta -= 1
        if len(assistant_message or "") > 1200:
            delta -= 1

        if old_energy <= 20 and delta < 1:
            delta = 1
        if old_energy >= 85 and delta > 1 and not has_restorative_keyword:
            delta = 1

        return max(-3, min(5, delta))

    def _apply_relationship(
        self,
        old_rel: RelationshipState,
        plan: ReactionPlan,
    ) -> RelationshipState:
        """更新关系状态"""
        new_rel = RelationshipState(
            character_id=old_rel.character_id,
            target_id=old_rel.target_id,
            affection=old_rel.affection,
            trust=old_rel.trust,
            familiarity=old_rel.familiarity,
            dependency=old_rel.dependency,
            security=old_rel.security,
            jealousy=old_rel.jealousy,
            updated_at=datetime.now().astimezone().isoformat(),
        )

        # 应用关系变化量
        deltas = plan.relationship_deltas
        if not deltas:
            return new_rel

        for field_name, delta in deltas.items():
            if field_name not in _MAX_DELTA_PER_TURN:
                continue

            max_delta = _MAX_DELTA_PER_TURN[field_name]
            # 限幅
            clamped_delta = max(-max_delta, min(max_delta, delta))

            old_value = getattr(new_rel, field_name, 50)
            new_value = old_value + clamped_delta
            # 边界约束 0-100
            new_value = max(0, min(100, new_value))
            setattr(new_rel, field_name, new_value)

        return new_rel
