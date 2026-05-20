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
_STATE_TURN_INTERVAL = 4

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
    from nbot.core.model_adapter import (
        build_chat_completion_payload,
        normalize_chat_completion_data,
        response_json_utf8,
        resolve_chat_completion_url,
    )
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
        '  "reason": "brief reason"\n'
        "}\n"
        "Use 0 for relationship fields that should not change. The relationship range is 0-100. "
        "Energy should recover when the user helps the character rest, eat, relax, feel safe, "
        "or receive affection/care; ordinary friendly comfort may be positive even without a major event."
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
    url = resolve_chat_completion_url(
        base_url,
        model=model,
        provider_type=provider_type,
        append_base_url_path=append_base_url_path,
    )
    payload = build_chat_completion_payload(
        model,
        messages,
        base_url=base_url,
        provider_type=provider_type,
        stream=False,
    )
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    response = requests.post(url, json=payload, headers=headers, timeout=60)
    response.raise_for_status()
    normalized = normalize_chat_completion_data(
        response_json_utf8(response),
        base_url=base_url,
        model=model,
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
    _STATE_TURN_COUNTERS[key] = _STATE_TURN_COUNTERS.get(key, 0) + 1
    _STATE_TURN_BUFFER.setdefault(key, []).append(
        {
            "user": user_message,
            "assistant": assistant_message,
        }
    )

    if _STATE_TURN_COUNTERS[key] < _STATE_TURN_INTERVAL:
        return state, relationship, False

    buffered_turns = _STATE_TURN_BUFFER.pop(key, [])
    try:
        adjustment = _call_state_model(buffered_turns, profile, state, relationship)
    except Exception as exc:
        _log.warning("[AutoState] state model call failed: %s", exc, exc_info=True)
        _STATE_TURN_BUFFER[key] = buffered_turns
        _STATE_TURN_COUNTERS[key] = _STATE_TURN_INTERVAL
        return state, relationship, False

    _STATE_TURN_COUNTERS[key] = 0
    if not adjustment:
        return state, relationship, False

    new_state, new_relationship = _apply_ai_adjustment(state, relationship, adjustment)
    _log.info(
        "[AutoState] applied %d-turn state adjustment: character=%s mood=%s intensity=%.2f reason=%s",
        _STATE_TURN_INTERVAL,
        state.character_id,
        new_state.mood,
        new_state.mood_intensity,
        str(adjustment.get("reason") or "")[:160],
    )
    return new_state, new_relationship, True
