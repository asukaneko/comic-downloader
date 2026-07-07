import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

from nbot.character.models import CharacterProfile, CharacterState, RelationshipState

_log = logging.getLogger(__name__)

_STATE_TURN_COUNTERS: Dict[str, int] = {}
_STATE_TURN_BUFFER: Dict[str, List[Dict[str, str]]] = {}
_STATE_TURN_INTERVAL = 2
_STATE_TURN_WINDOW = 5

# 角色体验质量评分缓存（由 AutoState 的 LLM 评估顺带产出，供 Review Pipeline 复用）
# key: "{character_id}:{target_id}:{conversation_id}" -> {"character_fidelity": float, ...}
_QUALITY_SCORE_CACHE: Dict[str, Dict[str, float]] = {}
_QUALITY_SCORE_FIELDS = ("character_fidelity", "immersion", "world_consistency", "risk")


def get_quality_scores(
    character_id: str,
    target_id: str = "",
    conversation_id: str = "",
) -> Dict[str, float]:
    """读取 AutoState 顺带评估出的角色体验质量评分（最近一次）。

    优先精确匹配 character:target:conversation，退而求其次只按 character_id 匹配，
    使非整除轮（AutoState 未运行的轮）也能拿到最近一次评分。
    返回空 dict 表示尚无评分。
    """
    if not character_id:
        return {}
    exact = _quality_key(character_id, target_id, conversation_id)
    if exact in _QUALITY_SCORE_CACHE:
        return dict(_QUALITY_SCORE_CACHE[exact])
    prefix = f"{character_id}:"
    for key in reversed(list(_QUALITY_SCORE_CACHE.keys())):
        if key.startswith(prefix):
            return dict(_QUALITY_SCORE_CACHE[key])
    return {}


def _quality_key(character_id: str, target_id: str, conversation_id: str) -> str:
    return ":".join(str(p or "") for p in (character_id, target_id, conversation_id))


def _store_quality_scores(
    character_id: str,
    target_id: str,
    conversation_id: str,
    raw_scores: Any,
) -> None:
    """从 LLM 评估结果中提取质量评分并缓存（限制缓存条目数防止内存膨胀）。"""
    if not character_id or not isinstance(raw_scores, dict):
        return
    cleaned: Dict[str, float] = {}
    for field_name in _QUALITY_SCORE_FIELDS:
        if field_name in raw_scores:
            cleaned[field_name] = _clamp_float(raw_scores.get(field_name), 0.0, 0.0, 1.0)
    if not cleaned:
        return
    key = _quality_key(character_id, target_id, conversation_id)
    # 防止无限膨胀：超过 200 条时丢弃最早的
    if len(_QUALITY_SCORE_CACHE) >= 200 and key not in _QUALITY_SCORE_CACHE:
        _QUALITY_SCORE_CACHE.pop(next(iter(_QUALITY_SCORE_CACHE)), None)
    _QUALITY_SCORE_CACHE[key] = cleaned

FALSE_VALUES = {"0", "false", "no", "off", "disabled"}
RELATIONSHIP_FIELDS = (
    "affection",
    "trust",
    "familiarity",
    "dependency",
    "security",
    "jealousy",
)
RELATIONSHIP_MAX_DELTA = {
    "affection": 8,
    "trust": 8,
    "familiarity": 6,
    "dependency": 6,
    "security": 8,
    "jealousy": 6,
}


def is_auto_state_enabled() -> bool:
    settings_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "data",
        "settings.json",
    )
    try:
        if os.path.exists(settings_file):
            with open(settings_file, "r", encoding="utf-8") as file:
                settings = json.load(file)
            features = settings.get("features") if isinstance(settings, dict) else {}
            if isinstance(features, dict) and "auto_character_state" in features:
                return bool(features.get("auto_character_state"))
    except Exception as exc:
        _log.debug("Failed to read auto character state setting: %s", exc)

    value = os.getenv("NBOT_AUTO_CHARACTER_STATE_ENABLED", "1").strip().lower()
    return value not in FALSE_VALUES


def _clean_json_text(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _parse_state_response(text: str) -> Dict[str, Any]:
    text = _clean_json_text(text)
    if not text:
        return {}

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}

    return parsed if isinstance(parsed, dict) else {}


def _clamp_float(value: Any, default: float, min_value: float, max_value: float) -> float:
    try:
        return max(min_value, min(max_value, float(value)))
    except (TypeError, ValueError):
        return default


def _clamp_int(value: Any, default: int, min_value: int, max_value: int) -> int:
    try:
        return max(min_value, min(max_value, int(round(float(value)))))
    except (TypeError, ValueError):
        return default


def _counter_key(
    character_id: str,
    scope_id: str,
    target_id: str,
    conversation_id: str = "",
    session_id: str = "",
) -> str:
    parts = [p for p in (character_id, target_id, session_id, conversation_id, scope_id) if p]
    return ":".join(parts) if parts else "default"


def _should_skip_turn(
    *,
    metadata: Optional[Dict[str, Any]] = None,
    result_error: Optional[str] = None,
) -> bool:
    if result_error:
        _log.info("[AutoState] skipped: AI response has error - %s", result_error)
        return True

    metadata = metadata or {}
    if metadata.get("is_heartbeat"):
        _log.info("[AutoState] skipped: heartbeat message")
        return True
    if metadata.get("skip_auto_state") or metadata.get("skip_auto_memory"):
        _log.info("[AutoState] skipped: skip_auto_state/skip_auto_memory flag")
        return True

    return False


def _call_state_model(
    turns: List[Dict[str, str]],
    profile: CharacterProfile,
    state: CharacterState,
    relationship: RelationshipState,
) -> Dict[str, Any]:
    from nbot.core.model_adapter import response_json_utf8
    from nbot.core.protocols import get_protocol
    from nbot.services.ai import refresh_runtime_ai_config

    runtime_ai = refresh_runtime_ai_config()
    base_url = runtime_ai.get("base_url") or ""
    model = runtime_ai.get("model") or ""
    provider_type = runtime_ai.get("provider_type") or "openai_compatible"
    api_key = runtime_ai.get("api_key") or ""
    append_base_url_path = runtime_ai.get("append_base_url_path", True)
    if not base_url or not model:
        return {}

    character_name = profile.name or profile.id or state.character_id or "the character"
    current_snapshot = {
        "mood": state.mood,
        "mood_intensity": state.mood_intensity,
        "energy": state.energy,
        "relationship": relationship.to_dict(),
    }

    turn_parts = []
    for i, turn in enumerate(turns, 1):
        turn_parts.append(
            f"--- Turn {i} ---\n"
            f"User:\n{turn.get('user', '')[:2000]}\n\n"
            f"{character_name}:\n{turn.get('assistant', '')[:2000]}"
        )

    system_prompt = (
        "You are a character-state evaluator, not the roleplay character.\n"
        "Read the recent conversation and decide how the character's runtime state should change.\n"
        "The state should be emotionally responsive: mood intensity may increase after meaningful "
        "positive or negative events, not only decay. Relationship values should change when the "
        "conversation shows durable signals, but avoid dramatic jumps for ordinary small talk.\n"
        "Return ONLY a JSON object with this schema:\n"
        "{\n"
        '  "mood": "short mood label or empty string to keep current mood",\n'
        '  "mood_intensity_delta": number between -0.35 and 0.35,\n'
        '  "energy_delta": integer between -8 and 12,\n'
        '  "relationship_deltas": {\n'
        '    "affection": integer, "trust": integer, "familiarity": integer,\n'
        '    "dependency": integer, "security": integer, "jealousy": integer\n'
        "  },\n"
        '  "quality_scores": {\n'
        '    "character_fidelity": number 0-1 (how in-character the replies stayed),\n'
        '    "immersion": number 0-1 (how immersive / emotionally engaging the exchange was),\n'
        '    "world_consistency": number 0-1 (how consistent with the established setting),\n'
        '    "risk": number 0-1 (risk of unsafe / contradictory / setting-breaking content; 0 = safe)\n'
        "  },\n"
        '  "personality_evolution": [\n'
        '    {"trait": "openness|warmland|confidence|trustfulness|independence|playfulness", '
        '"delta": integer between -10 and 10, "reason": "brief reason"}\n'
        "  ],\n"
        '  "reason": "brief reason"\n'
        "}\n"
        "Use 0 for relationship fields that should not change. The relationship range is 0-100. "
        "For quality_scores, judge the character's own replies in the conversation; "
        "use 1.0 for excellent, around 0.5 for acceptable, lower for breaks of character or setting. "
        "Energy should recover when the user helps the character rest, eat, relax, feel safe, "
        "or receive affection/care; ordinary friendly comfort may be positive even without a major event.\n"
        "personality_evolution should be EMPTY for ordinary chat. Only add an entry when a significant "
        "experience (prolonged conflict, major betrayal, deep intimacy, repeated rejection, life-changing "
        "event) would plausibly shift the character's personality. Use 1-2 entries at most. "
        "Each delta should be small (-10 to 10); personality shifts slowly."
    )

    user_prompt = (
        f"Character: {character_name}\n"
        f"Current state JSON:\n{json.dumps(current_snapshot, ensure_ascii=False)}\n\n"
        f"Recent conversation ({len(turns)} turns):\n\n"
        + "\n\n".join(turn_parts)
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    protocol = get_protocol(provider_type)
    url = protocol.resolve_url(
        base_url, model=model, append_base_url_path=append_base_url_path,
        api_key=api_key,
    )
    payload = protocol.build_payload(
        model, messages, stream=False,
        base_url=base_url, provider_type=provider_type,
    )
    headers = protocol.build_headers(api_key)

    response = requests.post(url, json=payload, headers=headers, timeout=60)
    response.raise_for_status()
    normalized = protocol.parse_response(
        response_json_utf8(response),
        model=model,
        base_url=base_url,
        provider_type=provider_type,
    )
    return _parse_state_response(normalized.content)


def _apply_ai_adjustment(
    state: CharacterState,
    relationship: RelationshipState,
    adjustment: Dict[str, Any],
) -> Tuple[CharacterState, RelationshipState]:
    new_state = CharacterState(
        character_id=state.character_id,
        scope_id=state.scope_id,
        mood=state.mood,
        mood_intensity=state.mood_intensity,
        energy=state.energy,
        scene=dict(state.scene),
        last_active_at=state.last_active_at,
        updated_at=datetime.now().isoformat(),
        personality_evolution=list(state.personality_evolution),
    )
    new_relationship = RelationshipState(
        character_id=relationship.character_id,
        target_id=relationship.target_id,
        affection=relationship.affection,
        trust=relationship.trust,
        familiarity=relationship.familiarity,
        dependency=relationship.dependency,
        security=relationship.security,
        jealousy=relationship.jealousy,
        updated_at=datetime.now().isoformat(),
    )

    mood = str(adjustment.get("mood") or "").strip()
    if mood:
        new_state.mood = mood[:40]

    intensity_delta = _clamp_float(
        adjustment.get("mood_intensity_delta"),
        0.0,
        -0.35,
        0.35,
    )
    new_state.mood_intensity = _clamp_float(
        new_state.mood_intensity + intensity_delta,
        new_state.mood_intensity,
        0.0,
        1.0,
    )

    energy_delta = _clamp_int(adjustment.get("energy_delta"), 0, -8, 12)
    new_state.energy = _clamp_int(new_state.energy + energy_delta, new_state.energy, 0, 100)

    deltas = adjustment.get("relationship_deltas") or {}
    if isinstance(deltas, dict):
        for field_name in RELATIONSHIP_FIELDS:
            raw_delta = deltas.get(field_name, 0)
            max_delta = RELATIONSHIP_MAX_DELTA[field_name]
            delta = _clamp_int(raw_delta, 0, -max_delta, max_delta)
            old_value = getattr(new_relationship, field_name)
            setattr(new_relationship, field_name, _clamp_int(old_value + delta, old_value, 0, 100))

    # 性格演化：累加 LLM 评估的 personality_evolution 条目
    evo_entries = adjustment.get("personality_evolution") or []
    if isinstance(evo_entries, list):
        from datetime import datetime as _dt
        turn_marker = _dt.now().astimezone().strftime("%Y-%m-%d")
        for entry in evo_entries:
            if not isinstance(entry, dict):
                continue
            trait = str(entry.get("trait") or "").strip()
            if not trait:
                continue
            delta_val = _clamp_int(entry.get("delta"), 0, -10, 10)
            if delta_val == 0:
                continue
            reason = str(entry.get("reason") or "").strip()[:200]
            new_state.personality_evolution.append({
                "trait": trait,
                "delta": delta_val,
                "reason": reason,
                "turn": turn_marker,
            })
        # 限制最多保留 20 条，超出则保留最近 20 条
        if len(new_state.personality_evolution) > 20:
            new_state.personality_evolution = new_state.personality_evolution[-20:]

    return new_state, new_relationship


def update_state_from_recent_turns(
    profile: CharacterProfile,
    state: CharacterState,
    relationship: RelationshipState,
    user_message: str,
    assistant_message: str,
    metadata: Optional[Dict[str, Any]] = None,
    conversation_id: str = "",
    result_error: Optional[str] = None,
) -> Tuple[CharacterState, RelationshipState, bool]:
    if not is_auto_state_enabled():
        return state, relationship, False
    if _should_skip_turn(metadata=metadata, result_error=result_error):
        return state, relationship, False

    user_message = (user_message or "").strip()
    assistant_message = (assistant_message or "").strip()
    if len(user_message) < 2 or len(assistant_message) < 2:
        _log.info(
            "[AutoState] skipped: message too short (user=%d, assistant=%d)",
            len(user_message),
            len(assistant_message),
        )
        return state, relationship, False

    metadata = metadata or {}
    character_id = (
        state.character_id
        or relationship.character_id
        or profile.id
        or profile.name
        or str(metadata.get("character_name") or metadata.get("sender_name") or "")
    )
    target_id = relationship.target_id or str(metadata.get("target_id") or metadata.get("user_id") or "")
    session_id = str(metadata.get("session_id") or "").strip()
    conversation_id = str(conversation_id or metadata.get("conversation_id") or "").strip()
    if not character_id or not target_id:
        _log.warning("[AutoState] skipped: character_id or target_id is empty")
        return state, relationship, False

    key = _counter_key(
        str(character_id).strip(),
        str(state.scope_id or "").strip(),
        str(target_id).strip(),
        conversation_id=conversation_id,
        session_id=session_id,
    )

    # 群聊模式：只有当一轮完整对话（用户提问 + 所有角色回复）完成后才增加计数器
    is_group_round_complete = bool(metadata.get("group_round_complete", False))

    # 添加到缓冲区（无论是否完成一轮）
    _STATE_TURN_BUFFER.setdefault(key, []).append(
        {
            "user": user_message,
            "assistant": assistant_message,
        }
    )
    _STATE_TURN_BUFFER[key] = _STATE_TURN_BUFFER[key][-_STATE_TURN_WINDOW:]

    # 群聊模式下，只有轮次完成才增加计数器；普通模式每次都增加
    if is_group_round_complete:
        _STATE_TURN_COUNTERS[key] = _STATE_TURN_COUNTERS.get(key, 0) + 1
    else:
        _STATE_TURN_COUNTERS[key] = _STATE_TURN_COUNTERS.get(key, 0) + 1

    # 会话级触发轮次覆盖：优先使用 metadata.auto_state_interval
    # 值为 0 或负数表示禁用 auto_state；正整数表示每 N 轮触发一次
    session_interval = _clamp_int(
        metadata.get("auto_state_interval"),
        _STATE_TURN_INTERVAL,  # 默认值
        0, 50,  # 合理范围：0~50
    )
    if session_interval <= 0:
        _log.debug("[AutoState] disabled for this session (auto_state_interval=0)")
        return state, relationship, False

    if _STATE_TURN_COUNTERS[key] < session_interval:
        return state, relationship, False

    buffered_turns = list(_STATE_TURN_BUFFER[key])
    try:
        adjustment = _call_state_model(buffered_turns, profile, state, relationship)
    except Exception as exc:
        _log.warning("[AutoState] state model call failed: %s", exc, exc_info=True)
        _STATE_TURN_COUNTERS[key] = 0
        return state, relationship, False

    _STATE_TURN_COUNTERS[key] = 0
    if not adjustment:
        return state, relationship, False

    # 缓存角色体验质量评分，供 Review Pipeline 复用
    _store_quality_scores(
        str(character_id).strip(),
        str(target_id).strip(),
        conversation_id,
        adjustment.get("quality_scores"),
    )

    new_state, new_relationship = _apply_ai_adjustment(state, relationship, adjustment)
    _log.info(
        "[AutoState] applied %d-turn state adjustment: character=%s mood=%s intensity=%.2f reason=%s",
        session_interval,
        state.character_id,
        new_state.mood,
        new_state.mood_intensity,
        str(adjustment.get("reason") or "")[:160],
    )
    return new_state, new_relationship, True
