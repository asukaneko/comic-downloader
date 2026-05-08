import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import requests

_log = logging.getLogger(__name__)


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
    return memories[:5]


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
    except Exception:
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
    return {
        "character_name": str(character_name or "").strip(),
        "target_id": str(target_id or "").strip(),
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


def _call_memory_model(user_message: str, assistant_message: str) -> List[Dict[str, Any]]:
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

    system_prompt = (
        "You are a memory extraction middleware, not a roleplay character. "
        "Extract only stable, future-useful memories from the latest turn. "
        "Remember user preferences, identity facts, durable relationship changes, "
        "long-term goals, promises, and stable fictional-world facts. "
        "Ignore ordinary chat, one-off requests, and claims invented only by the assistant. "
        "Return only a JSON array. If nothing is worth remembering, return []. "
        "Each item must have title, summary, content, and type ('long' or 'short')."
    )
    user_prompt = (
        "Latest conversation turn:\n\n"
        f"User:\n{user_message[:4000]}\n\n"
        f"Assistant:\n{assistant_message[:4000]}\n"
    )
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
        return 0
    if getattr(result, "error", None):
        return 0

    metadata = getattr(ctx.chat_request, "metadata", {}) or {}
    if metadata.get("is_heartbeat") or metadata.get("skip_auto_memory"):
        return 0

    user_message = (getattr(ctx.chat_request, "content", "") or "").strip()
    assistant_message = (getattr(result, "final_content", "") or "").strip()
    if len(user_message) < 2 or len(assistant_message) < 2:
        return 0

    memory_context = build_memory_context(ctx, callbacks)
    character_name = memory_context.get("character_name", "")
    target_id = memory_context.get("target_id", "")
    if not character_name and not target_id:
        return 0

    try:
        memories = _call_memory_model(user_message, assistant_message)
    except Exception as exc:
        _log.debug("Auto memory extraction failed: %s", exc)
        return 0

    if not memories:
        return 0

    try:
        from nbot.core.prompt import prompt_manager

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
        saved = 0
        for memory in memories:
            memory_key = (
                str(memory.get("title") or "").strip(),
                str(memory.get("content") or "").strip(),
            )
            if memory_key in existing_keys:
                continue
            if prompt_manager.add_memory(
                memory["title"],
                memory["content"],
                target_id,
                memory.get("summary"),
                memory.get("type", "long"),
                7,
                character_name or None,
            ):
                existing_keys.add(memory_key)
                saved += 1
                _log.info(
                    "[AutoMemory] saved memory: character=%s target=%s title=%s",
                    character_name or "-",
                    target_id or "-",
                    memory["title"],
                )
        if saved:
            _log.info(
                "[AutoMemory] saved %s memory item(s): character=%s target=%s",
                saved,
                character_name or "-",
                target_id or "-",
            )
        return saved
    except Exception as exc:
        _log.debug("Auto memory save failed: %s", exc)
        return 0
