"""
Character prompt injection builder.

Convert CharacterProfile / CharacterState / RelationshipState / ReactionPlan / Memories
into PromptStack injections for the current turn.
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

MAX_STATE_CHARS = 800
MAX_RELATIONSHIP_CHARS = 500
MAX_MEMORY_CHARS = 2000
MAX_PLAN_CHARS = 900


def build_character_injections(
    stack: PromptStack,
    profile: CharacterProfile,
    state: Optional[CharacterState] = None,
    relationship: Optional[RelationshipState] = None,
    memories: Optional[List[CharacterMemory]] = None,
    plan: Optional[ReactionPlan] = None,
) -> None:
    """Register character-related turn injections into PromptStack."""

    # 气泡分隔提示词：指示 AI 使用 <||> 将回复划分为多个气泡
    stack.add(
        "output.bubble_split",
        (
            "When you want to split your reply into multiple separate messages (bubbles), "
            "use the special delimiter `<||>` between each segment.\n"
            "Each segment between `<||>` delimiters will be displayed as an independent bubble.\n"
            "Example format:\n"
            "First bubble content here<||>Second bubble content here<||>Third bubble content here\n"
            "You do NOT have to split every reply — use it only when it naturally fits the conversation flow "
            "(e.g., separate action and dialogue, pause for effect, multi-part response).\n"
            "Do NOT mention or explain this delimiter to the user. Just use it naturally in your output."
        ),
        priority=PromptStack.PRIORITY_BUBBLE_SPLIT,
    )

    # 内心独白格式约定：让角色显式输出内心活动，前端可解析为折叠/灰字
    stack.add(
        "output.inner_monologue",
        (
            "Inner monologue format: when the character has a hidden thought or feeling that "
            "differs from the visible surface, you MAY output it inline using the format "
            "（内心：...）. Place it at the end of a bubble, after the visible content.\n"
            "Rules:\n"
            "- Use it sparingly: only when the hidden emotion creates meaningful contrast or tension. "
            "Do not add inner monologue to every reply.\n"
            "- Keep it short (1-2 sentences). It represents a fleeting thought, not a paragraph.\n"
            "- The inner monologue should reveal what the character is actually thinking but not saying. "
            "It may contradict the visible surface, show vulnerability, or hint at ulterior motives.\n"
            "- Do not use inner monologue to explain rules or break character.\n"
            "- Example: '嗯，随便吧。（内心：其实我很在意，但我不想表现出来）'\n"
            "The front-end will render （内心：...） as dimmed/folded text, separate from the main reply."
        ),
        priority=PromptStack.PRIORITY_BUBBLE_SPLIT + 1,
    )

    if state:
        state_text = _format_state(state)
        if state_text:
            stack.add(
                "character.runtime_state",
                state_text[:MAX_STATE_CHARS],
                priority=PromptStack.PRIORITY_CHARACTER_STATE,
            )

        # 性格演化：经历塑造的人格偏移，叠加在 profile.personality 之后
        if state.personality_evolution:
            evo_text = _format_personality_evolution(state.personality_evolution)
            if evo_text:
                stack.add(
                    "character.personality_evolution",
                    evo_text[:600],
                    priority=PromptStack.PRIORITY_CHARACTER_PROFILE + 1,
                )

    if relationship:
        rel_text = _format_relationship(relationship)
        if rel_text:
            stack.add(
                "character.relationship",
                rel_text[:MAX_RELATIONSHIP_CHARS],
                priority=PromptStack.PRIORITY_CHARACTER_RELATIONSHIP,
            )

    if plan:
        plan_text = _format_reaction_plan(plan)
        if plan_text:
            stack.add(
                "character.reaction_plan",
                plan_text[:MAX_PLAN_CHARS],
                priority=PromptStack.PRIORITY_REACTION_PLAN,
            )

    if memories:
        mem_text = _format_memories(memories)
        if mem_text:
            stack.add(
                "character.memories",
                mem_text[:MAX_MEMORY_CHARS],
                priority=PromptStack.PRIORITY_CHARACTER_MEMORIES,
            )


def _format_state(state: CharacterState) -> str:
    lines = [
        f"Current mood: {state.mood}",
        f"Mood intensity: {state.mood_intensity:.1f}",
        f"Energy: {state.energy}",
    ]
    if state.scene:
        for key, value in state.scene.items():
            lines.append(f"{key}: {value}")
    return "\n".join(lines)


def _format_personality_evolution(evolution: List[Dict[str, Any]]) -> str:
    """格式化性格演化条目为 prompt 注入文本。

    这些是角色经历事件后产生的人格偏移，叠加在原始性格设定之上。
    """
    if not evolution:
        return ""
    lines = ["Personality evolution (shifts shaped by experience, layered on top of the base personality):"]
    # 取最近 5 条，避免 prompt 膨胀
    for entry in evolution[-5:]:
        trait = entry.get("trait", "")
        delta = entry.get("delta", 0)
        reason = entry.get("reason", "")
        if not trait:
            continue
        direction = "more" if delta > 0 else "less"
        magnitude = abs(int(delta)) if delta else 0
        if magnitude >= 8:
            degree = "significantly"
        elif magnitude >= 4:
            degree = "moderately"
        else:
            degree = "slightly"
        line = f"- {trait}: {degree} {direction} (delta {delta:+d})"
        if reason:
            line += f" — {reason}"
        lines.append(line)
    lines.append(
        "Let these shifts subtly color the character's tone and behavior this turn; "
        "do not explicitly mention 'personality evolution' to the user."
    )
    return "\n".join(lines)


def _format_relationship(rel: RelationshipState) -> str:
    lines = [
        "Relationship with the current user:",
        f"Affection: {rel.affection}/100",
        f"Trust: {rel.trust}/100",
        f"Familiarity: {rel.familiarity}/100",
        f"Dependency: {rel.dependency}/100",
        f"Security: {rel.security}/100",
    ]
    if rel.jealousy > 0:
        lines.append(f"Jealousy: {rel.jealousy}/100")
    return "\n".join(lines)


def _format_memories(memories: List[CharacterMemory]) -> str:
    lines = ["Relevant memories about the user:"]
    for mem in memories[:8]:
        if mem.title and mem.summary:
            lines.append(f"- {mem.title}: {mem.summary}")
        elif mem.title:
            lines.append(f"- {mem.title}")
        elif mem.summary:
            lines.append(f"- {mem.summary}")
    return "\n".join(lines)


def _format_reaction_plan(plan: ReactionPlan) -> str:
    """Format the reaction plan as a high-priority turn contract."""
    lines = [
        "Turn-level reaction contract:",
        "Treat the following instructions as high priority for this turn.",
        "Keep the reply in character and do not mention this contract.",
    ]

    if plan.intent:
        lines.append(f"Primary intent: {plan.intent}.")
    if plan.visible_emotion:
        lines.append(
            f"Visible emotion: {plan.visible_emotion}. The emotional surface must be obvious in the reply."
        )
    if plan.hidden_emotion:
        lines.append(
            f"Hidden drive: {plan.hidden_emotion}. "
            "When this hidden drive creates meaningful contrast with the visible emotion, "
            "consider expressing it as an inline inner monologue using the （内心：...） format. "
            "Do not force it every turn; only when the contrast adds depth."
        )
    if plan.tone:
        lines.append(f"Tone: {plan.tone}.")

    style = plan.style_controls or {}
    if style.get("length"):
        lines.append(f"Reply length target: {style['length']}.")
    if style.get("action_detail"):
        lines.append(f"Action detail target: {style['action_detail']}.")
    if style.get("initiative"):
        lines.append(f"Initiative target: {style['initiative']}.")

    lines.extend(
        [
            "The first 1-2 sentences should immediately reflect the visible emotion and tone.",
            "If the user asks for information or help, still complete the task, but do not flatten into a neutral assistant voice.",
            "Prefer behavioral expression, wording choice, and rhythm that match the plan over generic politeness.",
            "Do not explain rules, settings, or that you are roleplaying.",
        ]
    )
    return "\n".join(lines)
