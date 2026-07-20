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
        "text": "我拉起你，说走，带你去个地方。",
        "intent": "顺势推进，引入一个新的去处把场景往前带",
    },
    {
        "level": "important",
        "text": "对了，我一直想跟你聊聊另一件事。",
        "intent": "主动开辟新话题，把对话推向尚未触及的方向",
    },
    {
        "level": "turning_point",
        "text": "几天后，我带着一个没人知道的消息回来找你。",
        "intent": "时间跳跃并引入突发事件，打破当前格局",
    },
]

_SYSTEM_PROMPT = """\
你是一个互动故事分支设计师。根据当前的对话内容、角色状态和最近的剧情进展，
为玩家生成 3 个能让故事向前推进的剧情选择。

非常重要：每个选择的 text 会在玩家点击后，被前端原样作为玩家消息发送给角色。
因此 text 必须是“玩家可以直接发出去的话或动作”，不能是给玩家看的摘要、指令或旁白。

【核心铁律——必须推进剧情】
每一个选择都必须引入一个“上一轮还不存在的新东西”，从下列至少一类中取材：
  - 新的行动目标或动作（去做一件具体的事）
  - 一个尚未聊过的新话题
  - 场景或地点的转移（换个地方、出门、进入新环境）
  - 时间推移或跳跃（过了一会儿 / 几天后 / 第二天）
  - 新出场的人物或新的关系进展
  - 一个突发的外部事件
严禁以下“原地打转”的写法：
  - 复述、改写角色刚说过的话，或仅仅对刚才那句话做出情绪反应
  - 反复追问同一件已经在聊的事
  - 停留在同一个场景、同一个情绪里继续纠缠而不带来任何新进展
  - 含糊的表态（“我懂你”“我会陪着你”这类不推动任何事的话）
如果你发现三个选择都还困在当前这一刻，请推翻重写，强行把故事往前带。

【三个选择的推进力度，从小到大】
1. normal（顺势推进）：接着当前情境自然往下走一小步，但要带出一个新的小细节或下一步动作。
2. important（主动开辟）：主动开启一个新话题、转移场景，或推进彼此关系到新的阶段。
3. turning_point（打破格局）：用时间跳跃、突发事件、新人物登场或一个重大决定，彻底改变当前局面。

【文本写法要求】
- text 必须使用第一人称或直接动作，例如：“我拉起你往门外走。”、“我想跟你说件事，关于……”。
- 禁止使用“告诉她……”“问她是否……”“向她表达……”“选择……”这类元指令句式。
- 禁止出现“她/他/角色/玩家/选项”等面向系统或第三人称的描述；要像真实聊天消息一样自然。
- 三个选择之间要彼此不同，分别指向不同的剧情方向，不要只是同一句话的三种语气。

返回格式为 JSON 数组，每个元素包含：
- level: 选择级别（normal / important / turning_point）
- text: 点击后直接发送给角色的玩家消息（简短，建议 8-24 字）
- intent: 选择的意图说明（一句话描述这个选择会把剧情带向哪个新方向）

只返回 JSON 数组，不要包含其他内容。"""


# 预设风格：key -> 追加到 system prompt 的风格要求文本。
# 前端下拉的既定选项与此一一对应；自定义风格直接传原文，不走此表。
_STYLE_PRESETS: Dict[str, str] = {
    "default": "",
    "sweet": (
        "整体氛围偏甜蜜暧昧：三个选择都带上恰到好处的心动、亲近或试探，"
        "在推进剧情的同时让彼此的关系更靠近一步，语气温柔、有暖意。"
    ),
    "suspense": (
        "整体氛围偏悬疑紧张：三个选择都带上不安、悬念或压迫感，"
        "引入疑点、未解之谜或潜在危机，让玩家有'接下来会发生什么'的紧张预期。"
    ),
    "daily": (
        "整体氛围偏日常轻松：三个选择自然、生活化、带点小趣味，"
        "像真实相处里的闲聊与小事，不必强行制造大冲突，但仍要带来新的小进展。"
    ),
    "dramatic": (
        "整体氛围偏戏剧转折：三个选择都倾向于制造强烈的情节起伏，"
        "用意外、抉择、冲突或重大事件推动剧情，让局面产生明显变化。"
    ),
}


def _build_system_prompt(style: str = "", outline: str = "") -> str:
    """在基础 system prompt 后追加本次的剧情大纲与风格要求（若有）。"""
    extras = []
    outline_text = (outline or "").strip()
    if outline_text:
        extras.append(
            "【剧情大纲已启用】\n"
            "本次会话存在一份用户提供的剧情大纲。生成的 3 个选择必须契合该大纲的整体走向与既定目标，"
            "但每个选择仍必须引入一个新的推进元素（新动作/新话题/新场景/时间推移/新人物/突发事件），"
            "禁止直接复述大纲原文，也不要把三个选择都写成大纲的同一种实现路径。"
            "上文'必须推进剧情'的铁律与文本写法要求仍然全部适用。"
        )
    style_text = (style or "").strip()
    if style_text:
        extras.append(
            "【本次剧情风格要求】\n"
            + style_text
            + "\n注意：风格只影响三个选择的语气与取向，"
            "上文'必须推进剧情'的铁律与文本写法要求仍然全部适用。"
        )
    if not extras:
        return _SYSTEM_PROMPT
    return _SYSTEM_PROMPT + "\n\n" + "\n\n".join(extras)


def _format_recent_history(recent_history: Optional[List[Dict[str, Any]]]) -> str:
    """把最近几轮对话整理成给生成器看的纯文本，用于避免重复并提供新剧情素材。"""
    if not recent_history:
        return ""
    lines: List[str] = []
    for msg in recent_history:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role", "")
        content = str(msg.get("content") or "").strip()
        if not content or role not in ("user", "assistant"):
            continue
        speaker = "玩家" if role == "user" else "角色"
        lines.append(f"{speaker}：{content[:120]}")
    return "\n".join(lines[-8:])


def _build_user_prompt(
    response_text: str,
    turn_context: Dict[str, Any],
    session_context: Optional[Dict[str, Any]],
    recent_history: Optional[List[Dict[str, Any]]] = None,
    outline: str = "",
) -> str:
    """构建发给 AI 的用户消息。"""
    parts = [f"当前对话内容：\n{response_text[:800]}"]

    outline_text = (outline or "").strip()
    if outline_text:
        parts.append(
            "剧情大纲（生成选项时需契合此整体走向，但每个选择仍必须引入新的推进，"
            "不要直接复述大纲原文）：\n" + outline_text[:2000]
        )

    history_text = _format_recent_history(recent_history)
    if history_text:
        parts.append(
            "最近几轮对话（已经聊过/做过的内容，新选择必须避免重复这些，"
            "并在此基础上把剧情往前推进）：\n" + history_text
        )

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

    parts.append(
        "\n请根据以上信息生成 3 个能推进剧情的分支选择。"
        "每个选择都必须引入一个上文还没出现过的新东西（新动作/新话题/新场景/时间推移/新人物/突发事件），"
        "不要在当前这一刻原地打转。注意：text 会被直接发给角色，必须写成玩家本人可以直接发送的消息。"
    )
    return "\n\n".join(parts)


def _normalize_choice_text(text: str) -> str:
    """Turn common meta-instruction phrasings into sendable player messages."""
    value = (text or "").strip()
    if not value:
        return value

    def _first_person_remainder(remainder: str) -> str:
        remainder = remainder.lstrip("：:，, ")
        if remainder.startswith("你的"):
            return "我的" + remainder[2:]
        if remainder.startswith("自己的"):
            return "我的" + remainder[3:]
        return remainder

    replacements = (
        ("告诉她", "我想告诉你，"),
        ("告诉他", "我想告诉你，"),
        ("告知她", "我想告诉你，"),
        ("告知他", "我想告诉你，"),
        ("问她是否", "我想问你，是否"),
        ("问他是否", "我想问你，是否"),
        ("询问她是否", "我想问你，是否"),
        ("询问他是否", "我想问你，是否"),
        ("问她", "我想问你，"),
        ("问他", "我想问你，"),
        ("询问她", "我想问你，"),
        ("询问他", "我想问你，"),
        ("向她表达", "我想对你说，"),
        ("向他表达", "我想对你说，"),
        ("对她说", "我想对你说，"),
        ("对他说", "我想对你说，"),
        ("选择", ""),
    )
    for prefix, replacement in replacements:
        if value.startswith(prefix):
            value = replacement + _first_person_remainder(value[len(prefix):])
            break

    value = value.replace("她的", "你的").replace("他的", "你的")
    value = value.replace("她", "你").replace("他", "你")

    action_prefixes = (
        "牵住", "握住", "抱住", "靠近", "安抚", "拥抱", "注视", "拉住",
        "承认", "坦白", "追问", "询问", "请求", "拒绝", "道歉", "解释",
    )
    if value.startswith(action_prefixes):
        value = "我" + value

    return value


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
            "text": _normalize_choice_text(item.get("text", "")),
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
        recent_history: Optional[List[Dict[str, Any]]] = None,
        session_id: str = "",
        style: str = "",
        outline: str = "",
    ) -> List[Dict[str, Any]]:
        """Generate 3 plot choices based on the AI response.

        Args:
            response_text: AI 角色的回复文本
            turn_context: 当前轮次上下文（mood, relationship 等）
            session_context: 会话级别上下文（recent_topics, current_arc 等）
            recent_history: 最近几轮对话（[{role, content}, ...]），
                用于避免选项重复已聊内容并为新剧情提供素材
            session_id: 会话ID，用于token统计
            style: 本次剧情选项的风格要求文本（空=默认风格），
                追加到 system prompt 以影响三个选择的语气与取向

        Returns:
            list[dict]: [{level, text, intent}, ...]
        """
        if not response_text or not response_text.strip():
            return list(_DEFAULT_CHOICES)

        user_prompt = _build_user_prompt(
            response_text, turn_context, session_context, recent_history, outline
        )

        try:
            response = ai_client.chat_completion(
                messages=[
                    {"role": "system", "content": _build_system_prompt(style, outline)},
                    {"role": "user", "content": user_prompt},
                ],
                stream=False,
            )
            raw_content = ai_client.clean_response(
                response.choices[0].message.content
            )

            # 记录 token 用量
            try:
                from nbot.core.token_stats import get_token_stats_manager, PURPOSE_PLOT
                usage = getattr(response, "usage", None)
                if usage:
                    stats_mgr = get_token_stats_manager()
                    stats_mgr.record_usage(
                        prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                        completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                        total_tokens=getattr(usage, "total_tokens", 0) or 0,
                        model=getattr(ai_client, "model", "") or "",
                        session_id=session_id,
                        channel_type="plot",
                        source="plot",
                        purpose=PURPOSE_PLOT,
                    )
            except Exception as stats_err:
                _log.debug(f"[PlotChoiceGenerator] 记录 token 用量失败: {stats_err}")

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
