"""Real-world time context for review and character continuity."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def _parse_datetime(value: str) -> datetime | None:
    value = str(value or "").strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _elapsed_label(seconds: int) -> str:
    if seconds <= 0:
        return "刚刚"
    minutes = seconds // 60
    if minutes < 1:
        return "刚刚"
    if minutes < 60:
        return f"{minutes}分钟"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}小时"
    days = hours // 24
    remaining_hours = hours % 24
    if remaining_hours:
        return f"{days}天{remaining_hours}小时"
    return f"{days}天"


def _continuity_level(seconds: int, has_previous: bool) -> str:
    if not has_previous:
        return "first_contact"
    if seconds < 30 * 60:
        return "continuous"
    if seconds < 6 * 60 * 60:
        return "short_gap"
    if seconds < 24 * 60 * 60:
        return "same_day_gap"
    if seconds < 7 * 24 * 60 * 60:
        return "days"
    return "long_absence"


def _roleplay_hint(level: str, elapsed_label: str) -> str:
    if level == "first_contact":
        return "这是第一次可用的现实时间记录；不要假装已经知道之前离线时发生的事。"
    if level == "continuous":
        return "现实中几乎没有间隔；把这轮当作连续对话自然承接。"
    if level == "short_gap":
        return f"现实中已经过去{elapsed_label}；可轻微承认时间流逝，但不要夸大成久别。"
    if level == "same_day_gap":
        return f"现实中已经过去{elapsed_label}；角色可以像在同一天稍后再次见面一样回应。"
    if level == "days":
        return f"现实中已经过去{elapsed_label}；角色应意识到隔了几天，可体现等待、生活延续或重新见面的感觉。"
    return f"现实中已经过去{elapsed_label}；角色应把这当作较长分别后的再次互动，但不要编造未经确认的具体经历。"


def build_real_time_context(
    *,
    previous_turn_time: str = "",
    current_time: str = "",
) -> dict[str, Any]:
    """Build a compact, serializable continuity context from real timestamps."""
    current = _parse_datetime(current_time) or datetime.now().astimezone()
    previous = _parse_datetime(previous_turn_time)
    elapsed_seconds = 0
    if previous:
        elapsed_seconds = max(0, int((current - previous).total_seconds()))

    has_previous = previous is not None
    level = _continuity_level(elapsed_seconds, has_previous)
    label = "初次记录" if not has_previous else _elapsed_label(elapsed_seconds)
    current_iso = current.isoformat(timespec="seconds")

    return {
        "current_time": current_iso,
        "previous_turn_time": previous.isoformat(timespec="seconds") if previous else "",
        "elapsed_seconds": elapsed_seconds,
        "elapsed_label": label,
        "continuity_level": level,
        "roleplay_hint": _roleplay_hint(level, label),
    }


def build_current_real_time_context(previous_turn_time: str = "") -> dict[str, Any]:
    return build_real_time_context(
        previous_turn_time=previous_turn_time,
        current_time=_now_iso(),
    )


def format_real_time_prompt_context(context: dict[str, Any]) -> str:
    if not context:
        return ""
    lines = [
        "## real_time.continuity",
        f"当前现实时间: {context.get('current_time', '')}",
    ]
    if context.get("previous_turn_time"):
        lines.append(f"上次互动时间: {context.get('previous_turn_time')}")
    lines.extend(
        [
            f"现实时间间隔: {context.get('elapsed_label', '')}",
            f"连续性等级: {context.get('continuity_level', '')}",
            f"角色扮演提示: {context.get('roleplay_hint', '')}",
            "把现实时间流逝当作角色生活连续性的一部分；可以体现等待、日常延续、重新见面的感觉。",
            "不要编造未经用户确认的具体离线经历、事件或承诺。",
        ]
    )
    return "\n".join(line for line in lines if line)
