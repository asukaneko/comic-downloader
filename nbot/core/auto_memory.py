import json
import logging
import os
import re
from typing import Any

import requests

_log = logging.getLogger(__name__)

# 记忆提取频率控制：同一角色每 N 轮对话才提取一次，使用累积的对话内容
_MEMORY_TURN_COUNTERS: dict[str, int] = {}
_MEMORY_TURN_INTERVAL = 6
# 对话缓冲区：按角色存储累积的对话轮次
_MEMORY_TURN_BUFFER: dict[str, list[dict[str, str]]] = {}

_STRUCTURED_MEMORY_CATEGORIES = {
    "user_persona",
    "character_persona",
    "important_event",
    "recent_digest",
}

_CATEGORY_ALIASES = {
    "user": "user_persona",
    "user_profile": "user_persona",
    "user_preference": "user_persona",
    "user_preferences": "user_persona",
    "persona_user": "user_persona",
    "relationship": "character_persona",
    "character": "character_persona",
    "character_profile": "character_persona",
    "character_attitude": "character_persona",
    "persona_character": "character_persona",
    "event": "important_event",
    "plot": "important_event",
    "important_events": "important_event",
    "world_event": "important_event",
    "digest": "recent_digest",
    "summary": "recent_digest",
    "recent_summary": "recent_digest",
    "dialogue_digest": "recent_digest",
    "diary": "recent_digest",
}


FALSE_VALUES = {"0", "false", "no", "off", "disabled"}


def is_auto_memory_enabled() -> bool:
    settings_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "data",
        "settings.json",
    )
    try:
        if os.path.exists(settings_file):
            with open(settings_file, encoding="utf-8") as file:
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


def _normalize_memory_category(value: Any) -> str:
    category = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return _CATEGORY_ALIASES.get(category, category if category in _STRUCTURED_MEMORY_CATEGORIES else "")


def _coerce_importance(value: Any) -> float:
    try:
        importance = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, importance))


def parse_memory_response(text: str) -> list[dict[str, Any]]:
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
        if any(key in parsed for key in ("title", "summary", "content")):
            parsed = [parsed]
        else:
            parsed = parsed.get("memories") or parsed.get("items") or []
    if not isinstance(parsed, list):
        return []

    memories: list[dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        content = str(item.get("content") or "").strip()
        summary = str(item.get("summary") or "").strip()
        mem_type = str(item.get("type") or "long").strip().lower()
        if mem_type not in {"long", "short"}:
            mem_type = "long"
        category = _normalize_memory_category(
            item.get("category")
            or item.get("kind")
            or item.get("memory_category")
            or item.get("target")
        )
        importance = _coerce_importance(item.get("importance"))
        if not title and summary:
            title = summary[:30]
        if not content and summary:
            content = summary
        if not title or not content:
            continue
        normalized = {
            "title": title[:80],
            "summary": (summary or content)[:200],
            "content": content[:2000],
            "type": mem_type,
        }
        if category:
            normalized["category"] = category
        if importance:
            normalized["importance"] = importance
        memories.append(normalized)
    return memories[:8]


def format_memories_for_prompt(memories: list[dict[str, Any]]) -> str:
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


def _has_structured_memories(memories: list[dict[str, Any]]) -> bool:
    return any(str(mem.get("category") or "") in _STRUCTURED_MEMORY_CATEGORIES for mem in memories)


def _memory_title(memory: dict[str, Any], fallback: str) -> str:
    return str(memory.get("title") or fallback).strip()[:80]


def _memory_summary(memory: dict[str, Any]) -> str:
    return str(memory.get("summary") or memory.get("content") or "").strip()[:500]


def _memory_content(memory: dict[str, Any]) -> str:
    title = str(memory.get("title") or "").strip()
    content = str(memory.get("content") or memory.get("summary") or "").strip()
    if title and content and title not in content:
        return f"{title}\n{content}"[:2000]
    return content[:2000]


def _save_structured_memories_to_memory_fs(
    memories: list[dict[str, Any]],
    *,
    character_id: str,
    target_id: str,
    session_id: str,
) -> int:
    if not character_id or not memories:
        return 0

    try:
        from nbot.memory.fs import get_memory_fs

        mfs = get_memory_fs()
        saved = 0
        for memory in memories:
            category = str(memory.get("category") or "")
            if category not in _STRUCTURED_MEMORY_CATEGORIES:
                continue

            content = _memory_content(memory)
            if not content:
                continue

            importance = _coerce_importance(memory.get("importance"))
            if category == "user_persona":
                if not target_id:
                    continue
                mfs.write(
                    mfs.path_user_persona(character_id, target_id),
                    character_id=character_id,
                    target_id=target_id,
                    title=_memory_title(memory, "用户人格记忆"),
                    content=content,
                    summary=_memory_summary(memory),
                    importance=importance or 0.6,
                    append=True,
                )
            elif category == "character_persona":
                if not target_id:
                    continue
                mfs.write(
                    mfs.path_character_persona(character_id, target_id),
                    character_id=character_id,
                    target_id=target_id,
                    title=_memory_title(memory, "角色人格记忆"),
                    content=content,
                    summary=_memory_summary(memory),
                    importance=importance or 0.6,
                    append=True,
                )
            elif category == "important_event":
                mfs.write(
                    mfs.path_important_events(character_id, session_id or target_id or "general"),
                    character_id=character_id,
                    target_id=target_id,
                    title=_memory_title(memory, "重要事件"),
                    content=content,
                    summary=_memory_summary(memory),
                    importance=importance or 0.8,
                    append=True,
                )
                # 同步追加到跨会话时间线
                _append_to_timeline(
                    mfs,
                    character_id=character_id,
                    target_id=target_id,
                    title=_memory_title(memory, "重要事件"),
                    content=content,
                )
            elif category == "recent_digest":
                if not target_id:
                    continue
                mfs.write(
                    mfs.path_recent_digest(character_id, target_id),
                    character_id=character_id,
                    target_id=target_id,
                    title=_memory_title(memory, "近期对话压缩摘要"),
                    content=content,
                    summary=_memory_summary(memory),
                    importance=importance or 0.4,
                    append=False,
                )
            saved += 1
        return saved
    except Exception as exc:
        _log.warning("[AutoMemory] 结构化记忆写入 MemoryFS 失败: %s", exc, exc_info=True)
        return 0


def _append_to_timeline(
    mfs,
    *,
    character_id: str,
    target_id: str,
    title: str,
    content: str,
) -> None:
    """将一条重要事件以带时间戳的格式追加到跨会话时间线。

    格式：[YYYY-MM-DD HH:MM] {title}: {content首行摘要}
    时间线文件由 _truncate_entries 自动保留最近 _MAX_TIMELINE_STORE 条。
    """
    if not character_id or not content:
        return
    try:
        from datetime import datetime

        timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
        # 取 content 第一行或前 120 字作为摘要，避免 timeline 单条过长
        first_line = content.split("\n", 1)[0].strip()
        snippet = first_line[:120] if len(first_line) > 120 else first_line
        entry = f"[{timestamp}] {title}: {snippet}"

        mfs.write(
            mfs.path_timeline(character_id),
            character_id=character_id,
            target_id=target_id,
            title="跨会话人生经历时间线",
            content=entry,
            summary="角色与用户共同经历的重要事件时间线",
            importance=0.8,
            append=True,
        )
    except Exception as exc:
        _log.debug("[AutoMemory] timeline append failed: %s", exc)


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


def build_memory_context(ctx, callbacks) -> dict[str, str]:
    context: dict[str, Any] = {}

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
    character_id = (
        context.get("character_id")
        or metadata.get("character_id")
        or character_name
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
        "character_id": str(character_id or "").strip(),
        "character_name": str(character_name or "").strip(),
        "target_id": str(target_id or "").strip(),
        "session_id": session_id,
    }


def inject_memories_into_messages(messages: list[dict[str, Any]], memory_text: str) -> None:
    if not memory_text:
        return

    for message in messages:
        if message.get("role") == "system":
            content = str(message.get("content") or "")
            if "## Cross-session character memory" not in content:
                message["content"] = content + memory_text
            return

    messages.insert(0, {"role": "system", "content": memory_text.strip()})


def _call_memory_model(turns: list[dict[str, str]],
                       character_name: str = "", user_name: str = "",
                       language: str = "") -> list[dict[str, Any]]:
    """调用 AI 模型从多轮对话中提取记忆

    Args:
        turns: 对话轮次列表，每项包含 user 和 assistant 两个字段
        character_name: 角色名称
        user_name: 用户名称
        language: 记忆输出语言
    """
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
        "You will receive multiple conversation turns. Reuse this one call to extract only compressed, future-useful memory. "
        "IMPORTANT: The memory MUST be specifically about or related to the character. "
        "Do NOT include generic information that is not tied to this character. "
        "Never store raw dialogue transcripts.\n"
        "Return JSON only. Use either [] if nothing is worth remembering, or an object with a memories array. "
        "Each memory item must contain category, title, summary, content, type ('long' or 'short'), and importance (0-1). "
        "Allowed categories:\n"
        "- user_persona: stable user preferences, boundaries, names, interaction style, emotional needs, or recurring traits.\n"
        "- character_persona: how the character's attitude, promises, habits, or relationship understanding toward the user changed.\n"
        "- important_event: promises, conflicts, confessions, separations, plot turns, confirmed setting changes, or world-state changes.\n"
        "- recent_digest: a compact summary of the recent turns only if it helps continuity; omit it for ordinary small talk.\n"
        "Use at most one item per category. Write summaries, not quotes. "
        "Ignore ordinary chat, one-off requests, and claims invented only by the assistant."
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
    resp_data = response_json_utf8(response)
    normalized = protocol.parse_response(
        resp_data,
        model=model,
        base_url=base_url,
        provider_type=provider_type,
    )

    # 记录 token 用量
    try:
        from nbot.core.token_stats import PURPOSE_MEMORY, get_token_stats_manager
        usage_data = resp_data.get("usage", {})
        if usage_data:
            stats_mgr = get_token_stats_manager()
            stats_mgr.record_usage(
                prompt_tokens=usage_data.get("prompt_tokens", 0) or 0,
                completion_tokens=usage_data.get("completion_tokens", 0) or 0,
                total_tokens=usage_data.get("total_tokens", 0) or 0,
                model=model or "",
                channel_type="memory",
                source="memory",
                purpose=PURPOSE_MEMORY,
            )
    except Exception:
        pass

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
    character_id = memory_context.get("character_id", "")
    character_name = memory_context.get("character_name", "")
    target_id = memory_context.get("target_id", "")
    session_id = memory_context.get("session_id", "")

    # 群聊模式：优先使用当前发言角色名，避免记忆混用"群聊"角色名
    if hasattr(ctx, 'metadata') and ctx.metadata:
        speaker_name = str(ctx.metadata.get("group_speaker_name") or "").strip()
        if speaker_name:
            character_name = speaker_name
            if not character_id:
                character_id = speaker_name

    if not character_name and not target_id:
        _log.warning("[AutoMemory] 跳过: character_name和target_id都为空，无法建立记忆关联")
        return 0

    # 使用 character_name + target_id + session_id 组合作为 key
    # session_id 用于区分 Web 端同一角色的不同会话
    parts = [p for p in (character_name, target_id, session_id) if p]
    counter_key = ":".join(parts) if parts else "default"

    # 群聊模式：只有当一轮完整对话（用户提问 + 所有角色回复）完成后才增加计数器
    is_group_round_complete = False
    if hasattr(ctx, 'metadata') and ctx.metadata:
        is_group_round_complete = bool(ctx.metadata.get("group_round_complete", False))

    # 添加到缓冲区（无论是否完成一轮）
    if counter_key not in _MEMORY_TURN_BUFFER:
        _MEMORY_TURN_BUFFER[counter_key] = []
    _MEMORY_TURN_BUFFER[counter_key].append({
        "user": user_message,
        "assistant": assistant_message,
    })

    # 群聊模式下，只有轮次完成才增加计数器；普通模式每次都增加
    if is_group_round_complete:
        turn_count = _MEMORY_TURN_COUNTERS.get(counter_key, 0) + 1
        _MEMORY_TURN_COUNTERS[counter_key] = turn_count
    else:
        turn_count = _MEMORY_TURN_COUNTERS.get(counter_key, 0) + 1
        _MEMORY_TURN_COUNTERS[counter_key] = turn_count

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

    if _has_structured_memories(memories):
        saved_count = _save_structured_memories_to_memory_fs(
            memories,
            character_id=character_id or character_name,
            target_id=target_id,
            session_id=session_id,
        )
        if saved_count:
            _log.info(
                "[AutoMemory] 已保存结构化记忆到 MemoryFS: character=%s count=%d",
                character_id or character_name,
                saved_count,
            )
        return saved_count

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
