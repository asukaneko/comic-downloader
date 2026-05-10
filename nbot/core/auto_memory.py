import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import requests

_log = logging.getLogger(__name__)

# 记忆提取频率控制：同一角色每 N 轮对话才提取一次，使用累积的对话内容
_MEMORY_TURN_COUNTERS: Dict[str, int] = {}
_MEMORY_TURN_INTERVAL = 6
# 对话缓冲区：按角色存储累积的对话轮次
_MEMORY_TURN_BUFFER: Dict[str, List[Dict[str, str]]] = {}


FALSE_VALUES = {"0", "false", "no", "off", "disabled"}


def is_auto_memory_enabled() -> bool:
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
            if isinstance(features, dict) and "auto_memory" in features:
                return bool(features.get("auto_memory"))
    except Exception as exc:
        _log.debug("Failed to read auto memory setting: %s", exc)

    value = os.getenv("NBOT_AUTO_MEMORY_ENABLED", "1").strip().lower()
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


def parse_memory_response(text: str) -> List[Dict[str, Any]]:
    text = _clean_json_text(text)
    if not text:
        return []

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", text)
        if not match:
            return []
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []

    if isinstance(parsed, dict):
        parsed = parsed.get("memories") or parsed.get("items") or []
    if not isinstance(parsed, list):
        return []

    memories: List[Dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        content = str(item.get("content") or "").strip()
        summary = str(item.get("summary") or "").strip()
        mem_type = str(item.get("type") or "long").strip().lower()
        if mem_type not in {"long", "short"}:
            mem_type = "long"
        if not title and summary:
            title = summary[:30]
        if not content and summary:
            content = summary
        if not title or not content:
            continue
        memories.append(
            {
                "title": title[:80],
                "summary": (summary or content)[:200],
                "content": content[:2000],
                "type": mem_type,
            }
        )
    return memories[:1]


def format_memories_for_prompt(memories: List[Dict[str, Any]]) -> str:
    if not memories:
        return ""

    lines = [
        "## Cross-session character memory",
        "The following memories belong to this character across conversations. Use them only when relevant, and do not mention that they were injected.",
        "",
    ]
    for mem in memories[:30]:
        title = str(mem.get("title") or "").strip()
        summary = str(mem.get("summary") or mem.get("content") or "").strip()
        if title and summary:
            lines.append(f"- {title}: {summary[:240]}")
        elif title:
            lines.append(f"- {title}")
        elif summary:
            lines.append(f"- {summary[:240]}")
    return "\n\n" + "\n".join(lines).rstrip()


def load_character_memories(character_name: str = "", target_id: str = "") -> str:
    if not character_name and not target_id:
        return ""
    try:
        from nbot.core.prompt import prompt_manager

        # Character memory is intentionally primary: this lets one character
        # remember across multiple sessions. target_id is kept for sessions
        # that do not have a character name yet.
        query_target_id = None if character_name else (target_id or None)
        memories = prompt_manager.get_memories(
            query_target_id,
            None,
            character_name or None,
        )
        return format_memories_for_prompt(memories)
    except Exception as exc:
        _log.debug("Failed to load auto memories: %s", exc)
        return ""


def build_memory_context(ctx, callbacks) -> Dict[str, str]:
    context: Dict[str, Any] = {}

    try:
        if hasattr(callbacks, "get_memory_context"):
            context = callbacks.get_memory_context(ctx) or {}
        else:
            context = callbacks.get_workspace_context(ctx) or {}
    except Exception as exc:
        _log.warning("[AutoMemory] 获取记忆上下文失败: %s", exc)
        context = {}

    metadata = getattr(ctx.chat_request, "metadata", {}) or {}
    character_name = (
        context.get("character_name")
        or metadata.get("character_name")
        or metadata.get("sender_name")
        or ""
    )
    target_id = (
        context.get("target_id")
        or context.get("user_id")
        or context.get("group_id")
        or getattr(ctx.chat_request, "user_id", None)
        or ""
    )
    # session_id 用于区分同一角色的不同 Web 会话
    session_id = str(context.get("session_id") or "").strip()
    return {
        "character_name": str(character_name or "").strip(),
        "target_id": str(target_id or "").strip(),
        "session_id": session_id,
    }


def inject_memories_into_messages(messages: List[Dict[str, Any]], memory_text: str) -> None:
    if not memory_text:
        return

    for message in messages:
        if message.get("role") == "system":
            content = str(message.get("content") or "")
            if "## Cross-session character memory" not in content:
                message["content"] = content + memory_text
            return

    messages.insert(0, {"role": "system", "content": memory_text.strip()})


def _call_memory_model(turns: List[Dict[str, str]],
                       character_name: str = "", user_name: str = "",
                       language: str = "") -> List[Dict[str, Any]]:
    """调用 AI 模型从多轮对话中提取记忆

    Args:
        turns: 对话轮次列表，每项包含 user 和 assistant 两个字段
        character_name: 角色名称
        user_name: 用户名称
        language: 记忆输出语言
    """
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
    if not base_url or not model:
        return []

    char_desc = f" The character's name is {character_name}." if character_name else ""
    user_desc = f" The user's name is {user_name}." if user_name else ""

    lang_names = {"zh": "Chinese (中文)", "en": "English", "ja": "Japanese (日本語)",
                  "ko": "Korean (한국어)", "zh-TW": "Traditional Chinese (繁體中文)"}
    lang_instruction = ""
    if language:
        lang_display = lang_names.get(language, language)
        lang_instruction = f"\nIMPORTANT: Write ALL memory fields (title, summary, content) in {lang_display}. Do NOT use any other language."

    system_prompt = (
        "You are a memory extraction middleware, not a roleplay character."
        f"{char_desc}{user_desc}\n"
        "You will receive multiple conversation turns. Your task is to consolidate them into exactly ONE concise memory entry. "
        "Synthesize all important, stable, future-useful information into a single summary. "
        "IMPORTANT: The memory MUST be specifically about or related to the character. "
        "Do NOT include generic information that is not tied to this character. "
        "For example, user preferences should be framed as what the user feels toward this character, "
        "and relationship facts must involve this character.\n"
        "Focus on: user preferences about this character, identity facts involving this character, "
        "durable relationship changes between the user and this character, "
        "long-term goals involving this character, promises made to or by this character, "
        "and stable fictional-world facts about this character.\n"
        "Ignore ordinary chat, one-off requests, claims invented only by the assistant, "
        "and anything not directly related to this character.\n"
        "If nothing worth remembering about this character, return []. "
        "Otherwise, return a JSON array with exactly ONE item containing title, summary, content, and type ('long' or 'short'). "
        "The content should be a well-organized consolidation of all noteworthy facts from the conversation."
        f"{lang_instruction}"
    )

    # 拼接多轮对话
    turn_parts = []
    for i, turn in enumerate(turns, 1):
        user_msg = turn.get("user", "")[:2000]
        asst_msg = turn.get("assistant", "")[:2000]
        turn_parts.append(
            f"--- Turn {i} ---\n"
            f"User ({user_name or 'User'}):\n{user_msg}\n\n"
            f"Assistant ({character_name or 'Assistant'}):\n{asst_msg}"
        )
    user_prompt = f"Conversation ({len(turns)} turns):\n\n" + "\n\n".join(turn_parts) + "\n"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    url = resolve_chat_completion_url(
        base_url,
        model=model,
        provider_type=provider_type,
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
    return parse_memory_response(normalized.content)


def extract_and_save_turn_memories(ctx, callbacks, result) -> int:
    if not is_auto_memory_enabled():
        _log.info("[AutoMemory] 跳过: 自动记忆功能未启用")
        return 0
    if getattr(result, "error", None):
        _log.info("[AutoMemory] 跳过: AI响应有错误 - %s", getattr(result, "error", None))
        return 0

    metadata = getattr(ctx.chat_request, "metadata", {}) or {}
    if metadata.get("is_heartbeat") or metadata.get("skip_auto_memory"):
        _log.info("[AutoMemory] 跳过: heartbeat或skip_auto_memory标记")
        return 0

    user_message = (getattr(ctx.chat_request, "content", "") or "").strip()
    assistant_message = (getattr(result, "final_content", "") or "").strip()
    if len(user_message) < 2 or len(assistant_message) < 2:
        _log.info("[AutoMemory] 跳过: 消息过短 (user=%d, assistant=%d)", len(user_message), len(assistant_message))
        return 0

    memory_context = build_memory_context(ctx, callbacks)
    character_name = memory_context.get("character_name", "")
    target_id = memory_context.get("target_id", "")
    session_id = memory_context.get("session_id", "")
    if not character_name and not target_id:
        _log.warning("[AutoMemory] 跳过: character_name和target_id都为空，无法建立记忆关联")
        return 0

    # 使用 character_name + target_id + session_id 组合作为 key
    # session_id 用于区分 Web 端同一角色的不同会话
    parts = [p for p in (character_name, target_id, session_id) if p]
    counter_key = ":".join(parts) if parts else "default"
    turn_count = _MEMORY_TURN_COUNTERS.get(counter_key, 0) + 1
    _MEMORY_TURN_COUNTERS[counter_key] = turn_count

    if counter_key not in _MEMORY_TURN_BUFFER:
        _MEMORY_TURN_BUFFER[counter_key] = []
    _MEMORY_TURN_BUFFER[counter_key].append({
        "user": user_message,
        "assistant": assistant_message,
    })

    if turn_count < _MEMORY_TURN_INTERVAL:
        return 0

    buffered_turns = _MEMORY_TURN_BUFFER.pop(counter_key, [])

    _log.info(
        "[AutoMemory] 达到%d轮，开始提取记忆: character=%s",
        _MEMORY_TURN_INTERVAL, character_name or "-",
    )

    user_name = ""
    if hasattr(ctx, 'chat_request'):
        user_name = getattr(ctx.chat_request, 'user_id', '') or ''
        metadata = getattr(ctx.chat_request, 'metadata', {}) or {}
        if not user_name:
            user_name = metadata.get('user_name', '') or metadata.get('sender', '') or ''

    language = ""
    try:
        from nbot.web.server import NBotWebServer
        server = NBotWebServer.get_instance()
        if server:
            language = (server.settings or {}).get("language", "") or ""
    except Exception:
        pass

    try:
        memories = _call_memory_model(buffered_turns,
                                      character_name=character_name, user_name=user_name,
                                      language=language)
    except Exception as exc:
        _log.warning("[AutoMemory] 记忆提取模型调用失败: %s", exc, exc_info=True)
        _MEMORY_TURN_BUFFER[counter_key] = buffered_turns
        _MEMORY_TURN_COUNTERS[counter_key] = _MEMORY_TURN_INTERVAL
        return 0

    if not memories:
        _log.info("[AutoMemory] 模型未返回任何值得保存的记忆")
        _MEMORY_TURN_COUNTERS[counter_key] = 0
        return 0

    _MEMORY_TURN_COUNTERS[counter_key] = 0

    try:
        from nbot.core.prompt import prompt_manager

        memory = memories[0]
        memory_key = (
            str(memory.get("title") or "").strip(),
            str(memory.get("content") or "").strip(),
        )
        existing = prompt_manager.get_memories(
            None if character_name else (target_id or None),
            None,
            character_name or None,
        )
        existing_keys = {
            (
                str(item.get("title") or "").strip(),
                str(item.get("content") or "").strip(),
            )
            for item in existing
        }
        if memory_key in existing_keys:
            _log.info("[AutoMemory] 记忆已存在，跳过: title=%s", memory.get("title", ""))
            return 0
        if not character_name:
            _log.info("[AutoMemory] 无角色名，跳过保存")
            return 0
        if prompt_manager.add_memory(
            memory["title"],
            memory["content"],
            target_id,
            memory.get("summary"),
            memory.get("type", "long"),
            7,
            character_name,
        ):
            _log.info(
                "[AutoMemory] 已保存记忆: character=%s title=%s",
                character_name, memory["title"],
            )
            return 1
        return 0
    except Exception as exc:
        _log.warning("[AutoMemory] 记忆保存失败: %s", exc, exc_info=True)
        return 0
