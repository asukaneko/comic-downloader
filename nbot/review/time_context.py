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
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None

    # 兼容旧数据：datetime.now().isoformat() 产生的 naive 时间
    if dt.tzinfo is None:
        dt = dt.astimezone()

    return dt


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


# ---------------------------------------------------------------------------
# 昼夜节律 / 作息状态
# ---------------------------------------------------------------------------

def _circadian_phase(hour: int) -> str:
    """根据 0-23 小时返回作息阶段标签。"""
    if 0 <= hour < 6:
        return "sleeping"
    if 6 <= hour < 9:
        return "morning"
    if 9 <= hour < 12:
        return "forenoon"
    if 12 <= hour < 14:
        return "noon"
    if 14 <= hour < 18:
        return "afternoon"
    if 18 <= hour < 22:
        return "evening"
    return "night"


def _circadian_label(phase: str) -> str:
    return {
        "sleeping": "深夜睡眠",
        "morning": "清晨起床",
        "forenoon": "上午时段",
        "noon": "午间休息",
        "afternoon": "下午时段",
        "evening": "傍晚晚间",
        "night": "深夜准备休息",
    }.get(phase, "日常")


def _circadian_roleplay_hint(phase: str, hour: int) -> str:
    """为每个作息阶段生成角色扮演提示。"""
    if phase == "sleeping":
        return (
            f"现在是凌晨{hour}点，角色应当处于睡眠状态。若被消息吵醒，反应可以带迷糊、"
            "困倦、不情愿，甚至略带起床气；不要主动展开长对话，节奏应放慢。"
        )
    if phase == "morning":
        return (
            f"现在是清晨{hour}点，角色可能刚起床不久，可以体现晨间状态"
            "（刚醒、洗漱、吃早餐、规划今天的事），语气可以略带慵懒或清新。"
        )
    if phase == "forenoon":
        return (
            f"现在是上午{hour}点，角色通常处于工作/学习/日常事务中，"
            "回复节奏可以略紧凑，体现被打断或抽空回应的感觉。"
        )
    if phase == "noon":
        return (
            f"现在是午间{hour}点，角色可能在吃饭或午休，"
            "可以体现餐后困倦、午睡被打扰或边吃边聊的状态。"
        )
    if phase == "afternoon":
        return (
            f"现在是下午{hour}点，角色处于下午时段，可以是继续工作、"
            "小憩、喝茶、散步等，状态相对松弛。"
        )
    if phase == "evening":
        return (
            f"现在是晚间{hour}点，角色已结束主要日程，处于放松时段，"
            "可以体现晚餐、洗澡、看电视/看书、准备休息等生活气息。"
        )
    return (
        f"现在是深夜{hour}点，角色应当正在准备睡觉或已经入睡，"
        "语气可以带倦意，互动节奏放缓，可体现'该睡了'的边界感。"
    )


def _circadian_energy_modifier(phase: str) -> int:
    """不同时段对角色精力的临时修正（仅本轮表现，不持久化）。"""
    return {
        "sleeping": -25,
        "morning": -8,
        "forenoon": 0,
        "noon": -5,
        "afternoon": 0,
        "evening": -3,
        "night": -15,
    }.get(phase, 0)


def build_circadian_state(now: datetime | None = None) -> dict[str, Any]:
    """根据当前本地时间构建角色昼夜节律状态。

    返回字段：
    - phase: 作息阶段 (sleeping/morning/forenoon/noon/afternoon/evening/night)
    - hour: 当前小时 (0-23)
    - label: 中文标签
    - roleplay_hint: 角色扮演提示
    - energy_modifier: 本轮精力临时修正值
    """
    current = now or datetime.now().astimezone()
    hour = current.hour
    phase = _circadian_phase(hour)
    return {
        "phase": phase,
        "hour": hour,
        "label": _circadian_label(phase),
        "roleplay_hint": _circadian_roleplay_hint(phase, hour),
        "energy_modifier": _circadian_energy_modifier(phase),
        "current_time": current.isoformat(timespec="seconds"),
    }


def format_circadian_prompt(context: dict[str, Any]) -> str:
    if not context:
        return ""
    lines = [
        f"作息阶段: {context.get('label', '')}（{context.get('hour', '')}点）",
        f"扮演提示: {context.get('roleplay_hint', '')}",
    ]
    modifier = context.get("energy_modifier", 0)
    if modifier:
        direction = "下降" if modifier < 0 else "上升"
        lines.append(f"本轮精力修正: {abs(modifier)}（{direction}）")
    lines.append("把当前时段当作角色真实生活的背景；不要刻意强调时间，但要让反应自然带有此时段的状态。")
    return "\n".join(line for line in lines if line)
