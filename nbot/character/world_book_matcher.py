"""
世界书关键词匹配器

扫描用户消息，根据关键词匹配返回应该注入的世界书条目。
"""

import json
import logging
import os
from typing import Dict, List, Optional

from nbot.character.models import WorldBook, WorldBookEntry

_log = logging.getLogger(__name__)

# 项目根目录（本文件位于 nbot/character/）
_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# ---------- UUID ↔ 角色名称 解析 ----------
# 前端 character_ids 可能存的是 custom_personality_presets 的 UUID，
# 但运行时 character_id 是角色名称。需要双向解析。

_preset_uuid_to_name_cache: Dict[str, str] = {}
_preset_cache_mtime: float = 0.0
_profile_names_cache: set = set()
_profile_names_mtime: float = 0.0


def _resolve_preset_uuids(base_dir: str) -> Dict[str, str]:
    """加载 custom_personality_presets.json，返回 {uuid: name} 映射（带缓存）"""
    global _preset_uuid_to_name_cache, _preset_cache_mtime
    presets_path = os.path.join(base_dir, "data", "web", "custom_personality_presets.json")
    try:
        mtime = os.path.getmtime(presets_path)
        if mtime == _preset_cache_mtime and _preset_uuid_to_name_cache:
            return _preset_uuid_to_name_cache
        with open(presets_path, "r", encoding="utf-8") as f:
            presets = json.load(f)
        mapping = {}
        for p in presets:
            pid = p.get("id", "")
            pname = p.get("name", "")
            if pid and pname:
                mapping[pid] = pname
        _preset_uuid_to_name_cache = mapping
        _preset_cache_mtime = mtime
        return mapping
    except Exception:
        return _preset_uuid_to_name_cache


def _load_profile_names(base_dir: str) -> set:
    """加载 profiles.json 中所有角色名称（带缓存）"""
    global _profile_names_cache, _profile_names_mtime
    profiles_path = os.path.join(base_dir, "data", "character", "profiles.json")
    try:
        mtime = os.path.getmtime(profiles_path)
        if mtime == _profile_names_mtime and _profile_names_cache:
            return _profile_names_cache
        with open(profiles_path, "r", encoding="utf-8") as f:
            profiles = json.load(f)
        _profile_names_cache = set(profiles.keys())
        _profile_names_mtime = mtime
        return _profile_names_cache
    except Exception:
        return _profile_names_cache


def _character_matches(character_id: str, book_character_ids: List[str], base_dir: str = "") -> bool:
    """检查 character_id 是否匹配世界书的 character_ids（支持 UUID 和名称混合）"""
    if not book_character_ids:
        return True  # 全局生效

    # 直接匹配（名称 ↔ 名称）
    if character_id in book_character_ids:
        return True

    if not base_dir:
        return False

    # UUID → 名称 解析
    uuid_to_name = _resolve_preset_uuids(base_dir)
    profile_names = _load_profile_names(base_dir)

    # case 1: character_id 是 UUID，需要转成名称再比对
    if character_id in uuid_to_name:
        resolved_name = uuid_to_name[character_id]
        if resolved_name in book_character_ids:
            return True

    # case 2: character_ids 里有 UUID，需要转成名称再和 character_id 比对
    for cid in book_character_ids:
        if cid in uuid_to_name:
            if uuid_to_name[cid] == character_id:
                return True
        # 也检查 profiles.json 中是否有此名称
        if cid in profile_names and cid == character_id:
            return True

    return False


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
        # 支持 UUID 和角色名称混合匹配
        if character_id and book.character_ids:
            if not _character_matches(character_id, book.character_ids, _BASE_DIR):
                _log.debug(
                    "[WorldBook] skip book %s: character_id=%s not in %s",
                    book.name, character_id, book.character_ids,
                )
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
            if not _character_matches(character_id, book.character_ids, _BASE_DIR):
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
