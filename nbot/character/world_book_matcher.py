"""
世界书关键词匹配器

扫描用户消息，根据关键词匹配返回应该注入的世界书条目。
"""

import logging
from typing import List, Optional

from nbot.character.models import WorldBook, WorldBookEntry

_log = logging.getLogger(__name__)


def match_entries(
    user_message: str,
    world_books: List[WorldBook],
    character_id: Optional[str] = None,
    max_total_chars: int = 3000,
) -> List[WorldBookEntry]:
    """扫描用户消息，返回所有命中的世界书条目

    Args:
        user_message: 用户发送的消息文本
        world_books: 已加载的世界书列表
        character_id: 当前角色 ID（用于过滤关联的世界书）
        max_total_chars: 命中条目总字符上限

    Returns:
        按 priority 降序排列的命中条目列表
    """
    if not user_message or not world_books:
        return []

    matched: List[WorldBookEntry] = []
    total_chars = 0

    for book in world_books:
        if not book.enabled:
            continue

        # 过滤角色关联：character_ids 为空表示全局生效
        if character_id and book.character_ids:
            if character_id not in book.character_ids:
                continue

        for entry in book.entries:
            if not entry.enabled or not entry.keywords:
                continue

            if _check_match(user_message, entry):
                entry_chars = len(entry.content)
                if total_chars + entry_chars > max_total_chars:
                    _log.debug(
                        "[WorldBook] stop injecting: entry %s (%d chars) exceeds limit %d/%d",
                        entry.name, entry_chars, total_chars, max_total_chars,
                    )
                    continue
                matched.append(entry)
                total_chars += entry_chars

    # 按 priority 降序排列
    matched.sort(key=lambda e: e.priority, reverse=True)

    if matched:
        _log.debug(
            "[WorldBook] matched %d entries, total %d chars: %s",
            len(matched), total_chars,
            [e.name for e in matched],
        )

    return matched


def _check_match(message: str, entry: WorldBookEntry) -> bool:
    """检查消息是否命中条目关键词"""
    check_msg = message if entry.case_sensitive else message.lower()

    results = []
    for keyword in entry.keywords:
        if not keyword:
            continue
        check_kw = keyword if entry.case_sensitive else keyword.lower()
        results.append(check_kw in check_msg)

    if not results:
        return False

    if entry.match_mode == "all":
        return all(results)
    else:
        return any(results)


def test_match(
    user_message: str,
    world_books: List[WorldBook],
    character_id: Optional[str] = None,
) -> List[dict]:
    """测试关键词匹配，返回详细的匹配信息（用于调试）

    Returns:
        [{"world_book_name": "...", "entry_name": "...", "matched_keywords": [...]}]
    """
    results = []

    for book in world_books:
        if not book.enabled:
            continue

        if character_id and book.character_ids:
            if character_id not in book.character_ids:
                continue

        for entry in book.entries:
            if not entry.enabled or not entry.keywords:
                continue

            check_msg = user_message if entry.case_sensitive else user_message.lower()
            matched_kw = []
            for keyword in entry.keywords:
                if not keyword:
                    continue
                check_kw = keyword if entry.case_sensitive else keyword.lower()
                if check_kw in check_msg:
                    matched_kw.append(keyword)

            all_non_empty = [k for k in entry.keywords if k]
            if entry.match_mode == "all" and len(matched_kw) == len(all_non_empty):
                results.append({
                    "world_book_name": book.name,
                    "world_book_id": book.id,
                    "entry_name": entry.name,
                    "entry_id": entry.id,
                    "matched_keywords": matched_kw,
                    "content_preview": entry.content[:200],
                })
            elif entry.match_mode == "any" and matched_kw:
                results.append({
                    "world_book_name": book.name,
                    "world_book_id": book.id,
                    "entry_name": entry.name,
                    "entry_id": entry.id,
                    "matched_keywords": matched_kw,
                    "content_preview": entry.content[:200],
                })

    return results
