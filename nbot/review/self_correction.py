"""
自我修正提示（Self-Correction Hint）

Review Pipeline 算出角色体验评分后，若某些维度低于阈值，
在这里生成一条「下一轮自我修正提示」并缓存。
CharacterRuntime.before_turn 会在下一轮把它注入 PromptStack，
从而让 AI 根据上一轮的不足自我纠正。

设计要点：
  - 与 auto_state 的 quality_scores 缓存类似，按 character:user:conversation 键存储
  - 只缓存「最近一次」修正提示，下一轮消费后清除（一次性）
  - 纯内存，限制条目数防止膨胀
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

_log = logging.getLogger(__name__)

# 低于该阈值的维度会触发对应的修正提示
_THRESHOLDS = {
    "character_fidelity": 0.6,
    "immersion": 0.5,
    "world_consistency": 0.6,
}
# risk 高于该阈值触发风险提示
_RISK_THRESHOLD = 0.6

# 各维度对应的修正提示文案
_HINTS = {
    "character_fidelity": "上一轮的回复有些脱离角色设定（OOC），这一轮请更严格地贴合角色的性格、说话方式和身份。",
    "immersion": "上一轮的代入感偏弱，这一轮请增强场景描写与情感表达，让对话更有沉浸感。",
    "world_consistency": "上一轮可能与既定世界观/设定有出入，这一轮请注意保持与世界设定的一致性。",
    "risk": "上一轮的内容存在偏离设定或前后矛盾的风险，这一轮请谨慎，确保内容安全、连贯、符合设定。",
}

_MAX_CACHE = 200

# key -> 修正提示文本（一次性，消费后清除）
_HINT_CACHE: Dict[str, str] = {}


def _key(character_id: str, user_id: str, conversation_id: str) -> str:
    return ":".join(str(p or "") for p in (character_id, user_id, conversation_id))


def build_correction_hint(scores) -> str:
    """根据 ReviewScore 生成自我修正提示文本，无需修正时返回空串。

    scores: ReviewScore 实例或 None
    """
    if scores is None:
        return ""
    parts = []
    for field_name, threshold in _THRESHOLDS.items():
        value = getattr(scores, field_name, None)
        # 评分为 0 通常表示尚未评估（AutoState 还没跑），跳过避免误报
        if value is None or value <= 0.0:
            continue
        if value < threshold:
            parts.append(_HINTS[field_name])

    risk = getattr(scores, "risk", 0.0) or 0.0
    if risk >= _RISK_THRESHOLD:
        parts.append(_HINTS["risk"])

    return "\n".join(parts)


def store_hint(character_id: str, user_id: str, conversation_id: str, hint: str) -> None:
    """缓存下一轮要注入的修正提示。空提示则清除已有缓存。"""
    if not character_id:
        return
    key = _key(character_id, user_id, conversation_id)
    if not hint:
        _HINT_CACHE.pop(key, None)
        return
    if len(_HINT_CACHE) >= _MAX_CACHE and key not in _HINT_CACHE:
        _HINT_CACHE.pop(next(iter(_HINT_CACHE)), None)
    _HINT_CACHE[key] = hint
    _log.debug("[SelfCorrection] stored hint for %s", key)


def consume_hint(character_id: str, user_id: str, conversation_id: str) -> Optional[str]:
    """读取并清除修正提示（一次性消费）。无则返回 None。"""
    if not character_id:
        return None
    key = _key(character_id, user_id, conversation_id)
    return _HINT_CACHE.pop(key, None)
