"""
Character prompt injection builder.

Convert CharacterProfile / CharacterState / RelationshipState / ReactionPlan / Memories
into PromptStack injections for the current turn.
"""

import logging
from typing import List, Optional

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
    if state:
        state_text = _format_state(state)
        if state_text:
            stack.add(
                "character.runtime_state",
                state_text[:MAX_STATE_CHARS],
                priority=PromptStack.PRIORITY_CHARACTER_STATE,
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
        lines.append(f"Hidden drive: {plan.hidden_emotion}.")
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
