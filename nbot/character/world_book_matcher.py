"""
世界书关键词匹配器

扫描用户消息，根据关键词匹配返回应该注入的世界书条目。
支持多源上下文召回：用户消息 + assistant 回复 + 历史上下文 + 场景状态。
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from nbot.character.models import WorldBook, WorldBookEntry

_log = logging.getLogger(__name__)

# 项目根目录（本文件位于 nbot/character/）
_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# ---------- 多源召回常量 ----------

SOURCE_WEIGHTS: Dict[str, int] = {
    "user": 50,
    "scene_state": 45,
    "assistant_recent": 30,
    "history": 20,
    "always": 100,
}

ENTRY_TYPE_PRIORITY: Dict[str, int] = {
    "relationship": 90,
    "rule": 80,
    "location": 70,
    "event": 60,
    "npc": 50,
    "faction": 45,
    "lore": 40,
    "style": 35,
    "secret": 30,
}


# ---------- 多源召回数据结构 ----------

@dataclass
class WorldBookRecallContext:
    """世界书召回上下文，描述本轮匹配可使用的所有信息"""

    latest_user_message: str = ""
    recent_messages: List[Dict[str, Any]] = field(default_factory=list)
    assistant_recent_text: str = ""
    history_text: str = ""
    scene: Dict[str, Any] = field(default_factory=dict)
    active_entry_ids: List[str] = field(default_factory=list)
    character_id: str = ""
    target_id: str = ""
    scope_id: str = ""


@dataclass
class WorldBookRecallConfig:
    """世界书召回配置"""

    recent_message_limit: int = 6
    max_history_chars: int = 2000
    max_total_chars: int = 3000
    max_entries: int = 8
    max_always_chars: int = 800
    max_scene_chars: int = 1000
    max_keyword_chars: int = 1200
    max_assistant_triggered_entries: int = 3
    min_assistant_priority: int = 20
    enable_assistant_trigger: bool = True
    enable_history_trigger: bool = True
    enable_scene_trigger: bool = True
    enable_cooldown: bool = True


@dataclass
class WorldBookMatchResult:
    """世界书匹配结果"""

    entry: WorldBookEntry
    trigger_sources: List[str] = field(default_factory=list)
    matched_keywords: List[str] = field(default_factory=list)
    score: int = 0


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


# ---------- 辅助函数 ----------

def _extract_assistant_recent_text(recent_messages: List[Dict[str, Any]], limit: int = 6) -> str:
    """从最近消息中提取 assistant 回复文本"""
    assistant_texts = []
    count = 0
    for msg in reversed(recent_messages):
        if msg.get("role") == "assistant" and msg.get("content"):
            assistant_texts.insert(0, msg["content"])
            count += 1
            if count >= limit:
                break
    return "\n".join(assistant_texts)


def _extract_history_text(recent_messages: List[Dict[str, Any]], max_chars: int = 2000) -> str:
    """从最近消息中提取上下文文本（user + assistant）"""
    parts = []
    total = 0
    for msg in reversed(recent_messages):
        content = msg.get("content", "")
        if not content:
            continue
        if total + len(content) > max_chars:
            break
        parts.insert(0, content)
        total += len(content)
    return "\n".join(parts)


def _extract_scene_text(scene: Dict[str, Any]) -> str:
    """从场景状态中提取可匹配文本"""
    if not scene:
        return ""
    parts = []
    for key, value in scene.items():
        if isinstance(value, str) and value:
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(str(v) for v in value if v)
    return " ".join(parts)


def _check_match_keywords(text: str, entry: WorldBookEntry) -> List[str]:
    """检查文本中命中的关键词，返回命中的关键词列表"""
    check_text = text if entry.case_sensitive else text.lower()
    matched = []
    for keyword in entry.keywords:
        if not keyword:
            continue
        check_kw = keyword if entry.case_sensitive else keyword.lower()
        if check_kw in check_text:
            matched.append(keyword)
    return matched


def _check_state_triggers(scene: Dict[str, Any], entry: WorldBookEntry) -> bool:
    """检查场景状态是否触发条目的 state_triggers"""
    if not entry.state_triggers or not scene:
        return False
    for field_name, trigger_values in entry.state_triggers.items():
        scene_value = scene.get(field_name)
        if scene_value is None:
            continue
        if isinstance(scene_value, str):
            if scene_value in trigger_values:
                return True
        elif isinstance(scene_value, list):
            if any(v in trigger_values for v in scene_value):
                return True
    return False


def _satisfies_match_mode(matched_keywords: List[str], entry: WorldBookEntry) -> bool:
    """检查匹配的关键词是否满足条目的 match_mode"""
    if not matched_keywords:
        return False
    if entry.match_mode == "all":
        non_empty = [k for k in entry.keywords if k]
        return len(matched_keywords) == len(non_empty)
    return True  # "any" mode


def _find_book_name(world_books: List[WorldBook], entry: WorldBookEntry) -> str:
    """查找条目所属的世界书名称"""
    for book in world_books:
        if entry in book.entries:
            return book.name
    return ""


# ---------- V2 多源召回匹配 ----------

def match_entries_v2(
    context: WorldBookRecallContext,
    world_books: List[WorldBook],
    character_id: Optional[str] = None,
    config: Optional[WorldBookRecallConfig] = None,
) -> List[WorldBookMatchResult]:
    """多源上下文召回匹配

    Args:
        context: 召回上下文
        world_books: 已加载的世界书列表
        character_id: 当前角色 ID
        config: 召回配置

    Returns:
        按 score 降序排列的匹配结果列表
    """
    if not world_books:
        return []

    if config is None:
        config = WorldBookRecallConfig()

    # 构建各源文本
    user_text = context.latest_user_message
    assistant_text = context.assistant_recent_text or _extract_assistant_recent_text(
        context.recent_messages, limit=config.recent_message_limit
    )
    history_text = context.history_text or _extract_history_text(
        context.recent_messages, max_chars=config.max_history_chars
    )

    results: List[WorldBookMatchResult] = []
    assistant_triggered_count = 0

    for book in world_books:
        if not book.enabled:
            continue

        # 角色过滤
        if character_id and book.character_ids:
            if not _character_matches(character_id, book.character_ids, _BASE_DIR):
                continue

        for entry in book.entries:
            if not entry.enabled:
                continue

            # 常驻条目
            if entry.always_on:
                results.append(WorldBookMatchResult(
                    entry=entry,
                    trigger_sources=["always"],
                    matched_keywords=[],
                    score=SOURCE_WEIGHTS["always"] + entry.priority + entry.weight,
                ))
                continue

            # 跳过无关键词且非常驻的条目
            if not entry.keywords and not entry.state_triggers:
                continue

            trigger_sources: List[str] = []
            all_matched_keywords: List[str] = []
            score = 0

            # 1. 用户消息匹配
            if "user" in entry.trigger_sources and user_text:
                user_matched = _check_match_keywords(user_text, entry)
                if _satisfies_match_mode(user_matched, entry):
                    trigger_sources.append("user")
                    all_matched_keywords.extend(user_matched)
                    score += SOURCE_WEIGHTS["user"]

            # 2. assistant 回复匹配
            if (config.enable_assistant_trigger
                    and "assistant_recent" in entry.trigger_sources
                    and assistant_text
                    and entry.priority >= config.min_assistant_priority
                    and assistant_triggered_count < config.max_assistant_triggered_entries):
                asst_matched = _check_match_keywords(assistant_text, entry)
                if _satisfies_match_mode(asst_matched, entry):
                    # assistant 不触发 secret 类型
                    if entry.entry_type != "secret":
                        trigger_sources.append("assistant_recent")
                        all_matched_keywords.extend(asst_matched)
                        score += SOURCE_WEIGHTS["assistant_recent"]
                        assistant_triggered_count += 1

            # 3. 历史上下文匹配
            if (config.enable_history_trigger
                    and "history" in entry.trigger_sources
                    and history_text):
                hist_matched = _check_match_keywords(history_text, entry)
                if _satisfies_match_mode(hist_matched, entry):
                    trigger_sources.append("history")
                    all_matched_keywords.extend(hist_matched)
                    score += SOURCE_WEIGHTS["history"]

            # 4. 场景状态匹配
            if (config.enable_scene_trigger
                    and "scene_state" in entry.trigger_sources
                    and _check_state_triggers(context.scene, entry)):
                trigger_sources.append("scene_state")
                score += SOURCE_WEIGHTS["scene_state"]

            # 只有至少命中一个源才加入结果
            if trigger_sources:
                score += entry.priority + entry.weight
                # 去重关键词
                unique_keywords = list(dict.fromkeys(all_matched_keywords))
                results.append(WorldBookMatchResult(
                    entry=entry,
                    trigger_sources=trigger_sources,
                    matched_keywords=unique_keywords,
                    score=score,
                ))

    # 排序：score 降序 → priority 降序 → entry_type 优先级 → 内容长度升序
    results.sort(key=lambda r: (
        -r.score,
        -r.entry.priority,
        -ENTRY_TYPE_PRIORITY.get(r.entry.entry_type, 0),
        len(r.entry.content),
    ))

    # 裁剪：max_entries
    if len(results) > config.max_entries:
        results = results[:config.max_entries]

    if results:
        _log.debug(
            "[WorldBook] v2 matched %d entries: %s",
            len(results),
            [(r.entry.name, r.trigger_sources, r.score) for r in results],
        )

    return results


# ---------- V2 测试匹配 ----------

def test_match_v2(
    context: WorldBookRecallContext,
    world_books: List[WorldBook],
    character_id: Optional[str] = None,
    config: Optional[WorldBookRecallConfig] = None,
) -> List[dict]:
    """测试多源关键词匹配，返回详细的匹配信息（用于调试）

    Returns:
        [{"world_book_name": "...", "entry_name": "...", "matched_keywords": [...],
          "trigger_sources": [...], "score": 95, "content_preview": "..."}]
    """
    results = match_entries_v2(context, world_books, character_id, config)
    return [
        {
            "world_book_name": _find_book_name(world_books, r.entry),
            "entry_name": r.entry.name,
            "entry_id": r.entry.id,
            "matched_keywords": r.matched_keywords,
            "trigger_sources": r.trigger_sources,
            "score": r.score,
            "content_preview": r.entry.content[:200],
        }
        for r in results
    ]


# ---------- V1 向后兼容接口 ----------

def match_entries(
    user_message: str,
    world_books: List[WorldBook],
    character_id: Optional[str] = None,
    max_total_chars: int = 3000,
) -> List[WorldBookEntry]:
    """扫描用户消息，返回所有命中的世界书条目（V1 兼容接口）

    内部使用 match_entries_v2 实现，保持向后兼容。

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

    context = WorldBookRecallContext(latest_user_message=user_message)
    config = WorldBookRecallConfig(max_total_chars=max_total_chars)
    results = match_entries_v2(context, world_books, character_id, config)
    return [r.entry for r in results]


def _check_match(message: str, entry: WorldBookEntry) -> bool:
    """检查消息是否命中条目关键词（V1 兼容）"""
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
    """测试关键词匹配，返回详细的匹配信息（V1 兼容接口）

    Returns:
        [{"world_book_name": "...", "entry_name": "...", "matched_keywords": [...]}]
    """
    if not user_message or not world_books:
        return []

    context = WorldBookRecallContext(latest_user_message=user_message)
    v2_results = test_match_v2(context, world_books, character_id)

    # 转换为 V1 格式
    return [
        {
            "world_book_name": r["world_book_name"],
            "world_book_id": r.get("entry_id", ""),
            "entry_name": r["entry_name"],
            "entry_id": r.get("entry_id", ""),
            "matched_keywords": r["matched_keywords"],
            "content_preview": r["content_preview"],
        }
        for r in v2_results
    ]
