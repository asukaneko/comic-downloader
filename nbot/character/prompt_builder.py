"""
角色提示词构建器

将 CharacterProfile / CharacterState / RelationshipState / ReactionPlan / Memories
转换为 PromptStack 注入项。
"""

import logging
from typing import Any, Dict, List, Optional

from nbot.character.models import (
    CharacterMemory,
    CharacterProfile,
    CharacterState,
    ReactionPlan,
    RelationshipState,
)
from nbot.character.prompt_stack import PromptStack

_log = logging.getLogger(__name__)

# 每类注入项的最大字符数
MAX_STATE_CHARS = 800
MAX_RELATIONSHIP_CHARS = 500
MAX_MEMORY_CHARS = 2000
MAX_PLAN_CHARS = 600


def build_character_injections(
    stack: PromptStack,
    profile: CharacterProfile,
    state: Optional[CharacterState] = None,
    relationship: Optional[RelationshipState] = None,
    memories: Optional[List[CharacterMemory]] = None,
    plan: Optional[ReactionPlan] = None,
) -> None:
    """将角色信息注册到 PromptStack

    Args:
        stack: 目标 PromptStack
        profile: 角色卡
        state: 角色运行时状态
        relationship: 关系状态
        memories: 相关记忆列表
        plan: 本轮反应计划
    """
    # 角色状态注入
    if state:
        state_text = _format_state(state)
        if state_text:
            stack.add(
                "character.runtime_state",
                state_text[:MAX_STATE_CHARS],
                priority=PromptStack.PRIORITY_CHARACTER_STATE,
            )

    # 关系状态注入
    if relationship:
        rel_text = _format_relationship(relationship)
        if rel_text:
            stack.add(
                "character.relationship",
                rel_text[:MAX_RELATIONSHIP_CHARS],
                priority=PromptStack.PRIORITY_CHARACTER_RELATIONSHIP,
            )

    # 记忆注入
    if memories:
        mem_text = _format_memories(memories)
        if mem_text:
            stack.add(
                "character.memories",
                mem_text[:MAX_MEMORY_CHARS],
                priority=PromptStack.PRIORITY_CHARACTER_MEMORIES,
            )

    # 反应计划注入
    if plan:
        plan_text = _format_reaction_plan(plan)
        if plan_text:
            stack.add(
                "character.reaction_plan",
                plan_text[:MAX_PLAN_CHARS],
                priority=PromptStack.PRIORITY_REACTION_PLAN,
            )


def _format_state(state: CharacterState) -> str:
    """格式化角色运行时状态"""
    lines = []
    lines.append(f"当前心情: {state.mood}")
    lines.append(f"情绪强度: {state.mood_intensity:.1f}")
    lines.append(f"精力: {state.energy}")
    if state.scene:
        for k, v in state.scene.items():
            lines.append(f"{k}: {v}")
    return "\n".join(lines)


def _format_relationship(rel: RelationshipState) -> str:
    """格式化关系状态"""
    lines = [
        "与当前用户的关系：",
        f"好感: {rel.affection}/100",
        f"信任: {rel.trust}/100",
        f"熟悉: {rel.familiarity}/100",
        f"依赖: {rel.dependency}/100",
        f"安全感: {rel.security}/100",
    ]
    if rel.jealousy > 0:
        lines.append(f"嫉妒: {rel.jealousy}/100")
    return "\n".join(lines)


def _format_memories(memories: List[CharacterMemory]) -> str:
    """格式化角色记忆"""
    lines = ["关于用户的记忆："]
    for mem in memories[:8]:
        if mem.title and mem.summary:
            lines.append(f"- {mem.title}: {mem.summary}")
        elif mem.title:
            lines.append(f"- {mem.title}")
        elif mem.summary:
            lines.append(f"- {mem.summary}")
    return "\n".join(lines)


def _format_reaction_plan(plan: ReactionPlan) -> str:
    """格式化反应计划为自然语言提示"""
    lines = ["本轮回复策略："]
    lines.append(f"- 角色表面情绪：{plan.visible_emotion}")
    if plan.hidden_emotion:
        lines.append(f"- 内心倾向：{plan.hidden_emotion}")

    style = plan.style_controls
    if style:
        if style.get("length"):
            length_map = {"short": "偏短", "medium": "适中", "long": "偏长"}
            lines.append(f"- 回复长度：{length_map.get(style['length'], style['length'])}")
        if style.get("action_detail"):
            detail_map = {"low": "少动作描写", "medium": "适度动作描写", "high": "丰富动作描写"}
            lines.append(f"- {detail_map.get(style['action_detail'], '适度动作描写')}")
        if style.get("initiative"):
            init_map = {"low": "被动回应", "medium": "适度主动", "high": "主动引导"}
            lines.append(f"- {init_map.get(style['initiative'], '适度主动')}")

    lines.append("- 不要解释规则，不要说自己在扮演角色")
    return "\n".join(lines)
