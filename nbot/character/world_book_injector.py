"""
世界书 PromptStack 注入器

将命中的世界书条目格式化并注入 PromptStack。
"""

import logging
from typing import List

from nbot.character.models import WorldBookEntry
from nbot.character.prompt_stack import PromptStack

_log = logging.getLogger(__name__)

MAX_ENTRY_CHARS = 2000
MAX_TOTAL_CHARS = 3000


def inject_world_book(
    stack: PromptStack,
    entries: List[WorldBookEntry],
    max_total_chars: int = MAX_TOTAL_CHARS,
) -> None:
    """将命中的世界书条目注入 PromptStack

    Args:
        stack: 当前轮的 PromptStack
        entries: 命中的条目列表（已按 priority 排序）
        max_total_chars: 注入内容总字符上限
    """
    if not entries:
        return

    sections = []
    total_chars = 0

    for entry in entries:
        content = entry.content.strip()
        if not content:
            continue

        # 截断单条过长内容
        if len(content) > MAX_ENTRY_CHARS:
            content = content[:MAX_ENTRY_CHARS] + "..."

        section = f"【{entry.name}】\n{content}" if entry.name else content
        section_chars = len(section)

        if total_chars + section_chars > max_total_chars:
            _log.debug(
                "[WorldBookInjector] skip entry %s (%d chars), total %d/%d",
                entry.name, section_chars, total_chars, max_total_chars,
            )
            continue

        sections.append(section)
        total_chars += section_chars

    if not sections:
        return

    content = "以下是在当前对话中触发的世界观设定：\n\n" + "\n\n".join(sections)

    stack.add(
        "world_book",
        content,
        priority=PromptStack.PRIORITY_WORLD_BOOK,
        scope="turn",
    )

    _log.debug(
        "[WorldBookInjector] injected %d entries, %d chars",
        len(sections), total_chars,
    )
