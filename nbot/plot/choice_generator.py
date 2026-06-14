"""
Plot Choice Generator

根据 AI 回复和角色状态生成 3 个分支选项，
驱动故事图谱的分支演进。
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from nbot.services.ai import ai_client

_log = logging.getLogger(__name__)

_DEFAULT_CHOICES = [
    {
        "level": "normal",
        "text": "继续当前的对话方向",
        "intent": "保持现状，稳步推进剧情",
    },
    {
        "level": "important",
        "text": "提出一个新的话题或问题",
        "intent": "深化关系或探索角色的另一面",
    },
    {
        "level": "turning_point",
        "text": "做出一个出乎意料的举动",
        "intent": "制造戏剧冲突或重大转折",
    },
]

_SYSTEM_PROMPT = """\
你是一个互动故事分支设计师。根据当前的对话内容和角色状态，
为玩家生成 3 个不同风格的剧情选择。

要求：
1. 第一个选择为保守型（normal）：维持现状，平稳推进
2. 第二个选择为推进型（important）：深化关系或探索新方向
3. 第三个选择为转折型（turning_point）：制造冲突或重大转折

返回格式为 JSON 数组，每个元素包含：
- level: 选择级别（normal / important / turning_point）
- text: 选择的显示文本（简短，15 字以内）
- intent: 选择的意图说明（一句话描述这个选择会带来什么效果）

只返回 JSON 数组，不要包含其他内容。"""


def _build_user_prompt(
    response_text: str,
    turn_context: Dict[str, Any],
    session_context: Optional[Dict[str, Any]],
) -> str:
    """构建发给 AI 的用户消息。"""
    parts = [f"当前对话内容：\n{response_text[:800]}"]

    mood = turn_context.get("mood", "")
    if mood:
        parts.append(f"角色当前心情：{mood}")

    relationship = turn_context.get("relationship", "")
    if relationship:
        parts.append(f"关系状态：{relationship}")

    if session_context:
        recent = session_context.get("recent_topics", [])
        if recent:
            parts.append(f"近期话题：{', '.join(recent[:5])}")

        arc = session_context.get("current_arc", "")
        if arc:
            parts.append(f"当前剧情线：{arc}")

    parts.append("\n请根据以上信息生成 3 个分支选择。")
    return "\n\n".join(parts)


def _parse_choices(raw: str) -> List[Dict[str, Any]]:
    """解析 AI 返回的 JSON，处理 markdown 围栏。"""
    cleaned = raw.strip()
    # 移除 markdown 代码围栏
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", cleaned, re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    parsed = json.loads(cleaned)
    if not isinstance(parsed, list):
        raise ValueError(f"Expected JSON array, got {type(parsed).__name__}")

    choices = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        choices.append({
            "level": item.get("level", "normal"),
            "text": item.get("text", ""),
            "intent": item.get("intent", ""),
        })
    return choices


class PlotChoiceGenerator:
    """AI 驱动的剧情分支选项生成器"""

    async def generate(
        self,
        response_text: str,
        turn_context: Dict[str, Any],
        session_context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Generate 3 plot choices based on the AI response.

        Args:
            response_text: AI 角色的回复文本
            turn_context: 当前轮次上下文（mood, relationship 等）
            session_context: 会话级别上下文（recent_topics, current_arc 等）

        Returns:
            list[dict]: [{level, text, intent}, ...]
        """
        if not response_text or not response_text.strip():
            return list(_DEFAULT_CHOICES)

        user_prompt = _build_user_prompt(
            response_text, turn_context, session_context
        )

        try:
            response = ai_client.chat_completion(
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                stream=False,
            )
            raw_content = ai_client.clean_response(
                response.choices[0].message.content
            )
            choices = _parse_choices(raw_content)

            # 确保至少有 3 个选择
            if len(choices) < 3:
                _log.warning(
                    "[PlotChoiceGenerator] AI returned %d choices, "
                    "padding with defaults",
                    len(choices),
                )
                while len(choices) < 3:
                    idx = len(choices)
                    choices.append(dict(_DEFAULT_CHOICES[idx]))

            return choices[:3]

        except Exception as e:
            _log.error(
                "[PlotChoiceGenerator] generation failed: %s", e,
                exc_info=True,
            )
            return list(_DEFAULT_CHOICES)
