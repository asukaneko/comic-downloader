"""
规则版 Review Pipeline

基于规则判断记忆写入、关系变化、剧情更新。
不调用大模型，适合 MVP 快速验证。
"""

from __future__ import annotations

import re
from typing import Optional

from nbot.review.models import (
    MemoryItem,
    PlotUpdate,
    RelationshipDelta,
    ReviewInput,
    ReviewOutput,
    ReviewScore,
    WorldBookUpdate,
)

# 触发信任/好感上升的关键词
_TRUST_UP_KEYWORDS = re.compile(
    r"谢谢|感谢|信任|放心|我相信你|靠你|我懂了|我明白了|承诺|约定", re.IGNORECASE
)
# 触发亲密度上升的关键词
_AFFECTION_UP_KEYWORDS = re.compile(
    r"喜欢|爱|想你|好想|亲爱|宝贝|心动|感动|暖|我爱", re.IGNORECASE
)
# 触发负面情绪（好感下降）的关键词
_AFFECTION_DOWN_KEYWORDS = re.compile(
    r"讨厌|烦死|滚|生气|失望|算了|拜拜|再见|冷漠|无聊", re.IGNORECASE
)


def run_rule_review(inp: ReviewInput) -> ReviewOutput:
    """执行规则版 Review，返回结构化建议。"""
    output = ReviewOutput(source="rule")

    choice = inp.selected_choice or {}
    choice_level = choice.get("level", "")
    user_msg = inp.user_message or ""
    assistant_msg = inp.assistant_message or ""
    combined = user_msg + " " + assistant_msg

    # --- 关系变化 ---
    affection_delta = 0
    trust_delta = 0
    familiarity_delta = 1  # 每轮对话默认 +1 熟悉度

    if _TRUST_UP_KEYWORDS.search(user_msg):
        trust_delta += 1
    if _AFFECTION_UP_KEYWORDS.search(combined):
        affection_delta += 1
    if _AFFECTION_DOWN_KEYWORDS.search(user_msg):
        affection_delta -= 1

    # 剧情选择影响关系
    if choice_level == "important":
        affection_delta += 1
        trust_delta += 1
    elif choice_level == "turning_point":
        affection_delta += 2
        trust_delta += 1

    reason = ""
    if affection_delta != 0 or trust_delta != 0 or familiarity_delta > 0:
        parts = []
        if affection_delta > 0:
            parts.append("用户表达了亲密情感")
        elif affection_delta < 0:
            parts.append("用户表达了负面情绪")
        if trust_delta > 0:
            parts.append("用户表达了信任或感谢")
        if choice_level in ("important", "turning_point"):
            parts.append(f"选择了 {choice_level} 级剧情分支")
        if familiarity_delta > 0:
            parts.append("正常对话推进熟悉度")
        reason = "；".join(parts) + "。" if parts else ""

    total_delta = abs(affection_delta) + abs(trust_delta) + familiarity_delta
    if total_delta > 0:
        output.relationship_delta = RelationshipDelta(
            affection=affection_delta,
            trust=trust_delta,
            familiarity=familiarity_delta,
            reason=reason,
            conversation_id=inp.conversation_id,
            plot_node_id=choice.get("node_id", ""),
        )

    # --- 记忆写入 ---
    memory_value = _calc_memory_value(inp, choice_level)
    should_write = (
        memory_value >= 0.65
        or choice_level in ("important", "turning_point", "ending")
        or total_delta >= 3
    )

    if should_write and (inp.user_message or inp.assistant_message):
        output.should_write_memory = True
        output.memory_items.append(MemoryItem(
            target="user",
            mem_type="relationship" if choice_level == "important" else (
                "event" if choice_level == "turning_point" else "short"
            ),
            title=_extract_memory_title(choice, inp),
            content=_extract_memory_content(inp),
            importance=memory_value,
            ttl="long" if choice_level in ("turning_point", "ending") else (
                "long" if memory_value >= 0.8 else "short"
            ),
        ))

    # --- 剧情更新 ---
    if choice_level in ("important", "turning_point", "ending"):
        output.plot_update = PlotUpdate(
            should_create_node=True,
            level=choice_level,
            summary=choice.get("intent", ""),
            title=choice.get("text", "")[:30],
        )

    # --- 世界书更新（仅 turning_point/ending 触发） ---
    if choice_level in ("turning_point", "ending"):
        output.world_book_update = WorldBookUpdate(
            should_update=True,
            reason=f"用户选择了 {choice_level} 级剧情分支：{choice.get('text', '')[:50]}",
        )

    # --- 评分 ---
    output.scores = ReviewScore(
        memory_value=memory_value,
        story_progress=_calc_story_progress(choice_level),
        relationship_progress=min(1.0, total_delta / 5.0),
        user_engagement=_calc_engagement(user_msg),
        risk=0.0,
    )

    # 普通闲聊且无剧情选择 → 标记 skipped，减少日志噪音
    if not choice_level and memory_value < 0.3:
        output.skipped = True

    return output


def _calc_memory_value(inp: ReviewInput, choice_level: str) -> float:
    """估算本轮对话的记忆价值（0-1）。"""
    score = 0.0
    if choice_level == "turning_point":
        score = 0.9
    elif choice_level == "important":
        score = 0.8
    elif choice_level == "ending":
        score = 0.95
    else:
        # 基于消息长度和关键词简单估算
        user_len = len(inp.user_message or "")
        if user_len > 100:
            score += 0.3
        elif user_len > 50:
            score += 0.2
        if _TRUST_UP_KEYWORDS.search(inp.user_message or ""):
            score += 0.2
        if _AFFECTION_UP_KEYWORDS.search(inp.user_message or ""):
            score += 0.2
    return min(1.0, score)


def _calc_story_progress(choice_level: str) -> float:
    return {"normal": 0.2, "important": 0.6, "turning_point": 0.9, "ending": 1.0}.get(
        choice_level, 0.1
    )


def _calc_engagement(user_msg: str) -> float:
    length = len(user_msg or "")
    if length > 200:
        return 0.9
    if length > 80:
        return 0.7
    if length > 30:
        return 0.5
    return 0.3


def _extract_memory_title(choice: dict, inp: ReviewInput) -> str:
    text = choice.get("text", "")
    if text:
        return text[:30]
    return (inp.user_message or "")[:30] or "对话记录"


def _extract_memory_content(inp: ReviewInput) -> str:
    parts = []
    if inp.user_message:
        parts.append(f"用户：{inp.user_message[:200]}")
    if inp.assistant_message:
        parts.append(f"角色：{inp.assistant_message[:200]}")
    return "\n".join(parts)
