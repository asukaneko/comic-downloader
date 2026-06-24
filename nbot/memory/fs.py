"""
MemoryFS — 记忆逻辑文件系统

作为现有 PromptManager 记忆系统的上层组织层。
通过 path 字段把记忆条目组织成角色可读的逻辑视图。

存储：data/web/memory_fs.json（path → MemoryFile 的索引）
注意：MemoryFS 独立持久化到 memory_fs.json，不自动写入底层 memory_service。
如需同步到底层记忆系统，需在调用方显式处理。
"""

from __future__ import annotations

import json
import logging
import os

from nbot.memory.models import MemoryFile

_log = logging.getLogger(__name__)

_DEFAULT_DATA_DIR = "data/web"
_FS_INDEX_FILE = "memory_fs.json"

# 防止单文件无限膨胀
_MAX_MEMORY_FILE_CHARS = 4000
_MAX_DIARY_ENTRIES = 30
_MAX_PLOT_ENTRIES = 50

_MEMORY_CATEGORY_META = {
    "user_persona": {"label": "用户人格", "injects_to_prompt": True, "order": 10},
    "character_persona": {"label": "角色人格", "injects_to_prompt": True, "order": 20},
    "important_event": {"label": "重要事件", "injects_to_prompt": True, "order": 30},
    "recent_digest": {"label": "近期摘要", "injects_to_prompt": True, "order": 40},
    "legacy": {"label": "旧版/其他", "injects_to_prompt": False, "order": 90},
}

_MEMORY_CATEGORY_ALIASES = {
    "user": "user_persona",
    "user_profile": "user_persona",
    "user_preference": "user_persona",
    "user_preferences": "user_persona",
    "persona_user": "user_persona",
    "character": "character_persona",
    "character_profile": "character_persona",
    "character_attitude": "character_persona",
    "persona_character": "character_persona",
    "relationship": "character_persona",
    "event": "important_event",
    "events": "important_event",
    "important_events": "important_event",
    "plot": "important_event",
    "plot_summary": "important_event",
    "world_event": "important_event",
    "digest": "recent_digest",
    "summary": "recent_digest",
    "recent_summary": "recent_digest",
    "dialogue_digest": "recent_digest",
    "diary": "recent_digest",
}

# 全局单例
_memory_fs: MemoryFS | None = None


def _truncate_entries(content: str, path: str) -> str:
    """截断过长内容，保留最近的条目，不切断单条记忆。

    根据路径类型选择不同的保留策略：
    - diary: 保留最近 _MAX_DIARY_ENTRIES 条
    - plot:  保留最近 _MAX_PLOT_ENTRIES 条
    - 其他:  按条目从旧到新丢弃，直到总长度不超限
    """
    entries = content.split("\n\n")
    if "diary" in path:
        max_entries = _MAX_DIARY_ENTRIES
    elif "plot" in path:
        max_entries = _MAX_PLOT_ENTRIES
    else:
        max_entries = len(entries)  # 不限条目数，只限总字符

    if len(entries) > max_entries:
        entries = entries[-max_entries:]

    # 按条目从旧到新丢弃，直到总长度不超 _MAX_MEMORY_FILE_CHARS
    while entries and len("\n\n".join(entries)) > _MAX_MEMORY_FILE_CHARS:
        entries.pop(0)

    return "\n\n".join(entries)


def normalize_memory_category(value) -> str:
    category = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if category in _MEMORY_CATEGORY_META and category != "legacy":
        return category
    return _MEMORY_CATEGORY_ALIASES.get(category, "")


def describe_memory_path(path: str) -> dict:
    path = str(path or "")
    category = "legacy"
    if path.endswith("/user_persona.md"):
        category = "user_persona"
    elif path.endswith("/character_persona.md"):
        category = "character_persona"
    elif path.endswith("/recent_digest.md"):
        category = "recent_digest"
    elif "/events/" in path or "/plot/" in path:
        category = "important_event"

    meta = _MEMORY_CATEGORY_META[category]
    return {
        "category": category,
        "category_label": meta["label"],
        "injects_to_prompt": bool(meta["injects_to_prompt"]),
        "category_order": meta["order"],
    }


class MemoryFS:
    """记忆逻辑文件系统

    路径规范：
        characters/{char_id}/general.md           角色通用信息
        characters/{char_id}/users/{user_id}/user_persona.md       用户人格/偏好画像
        characters/{char_id}/users/{user_id}/character_persona.md  角色对用户的关系理解
        characters/{char_id}/users/{user_id}/recent_digest.md      压缩后的近期摘要
        characters/{char_id}/events/{conversation_id}.md           重要事件
        characters/{char_id}/users/{user_id}.md                    旧版用户关系摘要
        characters/{char_id}/diary/daily.md                        旧版日记路径
        characters/{char_id}/diary/weekly.md       本周摘要
        characters/{char_id}/plot/{conv_id}.md    剧情摘要
        characters/{char_id}/world/events.md       世界事件记录
    """

    def __init__(self, data_dir: str = _DEFAULT_DATA_DIR):
        self._index_file = os.path.join(data_dir, _FS_INDEX_FILE)
        self._index: dict[str, MemoryFile] = {}
        self._load()

    # ------------------------------------------------------------------
    # 核心接口
    # ------------------------------------------------------------------

    def read(self, path: str) -> MemoryFile | None:
        """读取逻辑路径对应的记忆文件。"""
        return self._index.get(path)

    def write(
        self,
        path: str,
        *,
        character_id: str = "",
        target_id: str = "",
        title: str = "",
        content: str = "",
        summary: str = "",
        tags: list[str] | None = None,
        importance: float = 0.0,
        source_event_id: str = "",
        memory_ids: list[str] | None = None,
        append: bool = False,
    ) -> MemoryFile:
        """写入或更新逻辑路径的记忆文件。

        append=True 时将 content 追加到现有内容末尾（用于日记）。
        """
        existing = self._index.get(path)

        if existing and append:
            new_content = existing.content + "\n\n" + content if existing.content else content
            # 截断：防止无限膨胀（diary/plot 按条目数，其他按字符数）
            needs_truncation = (
                ("diary" in path and new_content.count("\n\n") >= _MAX_DIARY_ENTRIES)
                or ("plot" in path and new_content.count("\n\n") >= _MAX_PLOT_ENTRIES)
                or len(new_content) > _MAX_MEMORY_FILE_CHARS
            )
            if needs_truncation:
                new_content = _truncate_entries(new_content, path)
            new_ids = list(set((existing.memory_ids or []) + (memory_ids or [])))
            mf = MemoryFile(
                path=path,
                character_id=character_id or existing.character_id,
                target_id=target_id or existing.target_id,
                title=title or existing.title,
                content=new_content,
                summary=summary or existing.summary,
                tags=tags if tags is not None else existing.tags,
                importance=max(importance, existing.importance),
                version=existing.version + 1,
                source_event_id=source_event_id or existing.source_event_id,
                memory_ids=new_ids,
            )
        elif existing:
            mf = MemoryFile(
                path=path,
                character_id=character_id or existing.character_id,
                target_id=target_id or existing.target_id,
                title=title or existing.title,
                content=content if content else existing.content,
                summary=summary if summary else existing.summary,
                tags=tags if tags is not None else existing.tags,
                importance=importance if importance > 0 else existing.importance,
                version=existing.version + 1,
                source_event_id=source_event_id or existing.source_event_id,
                memory_ids=list(set((existing.memory_ids or []) + (memory_ids or []))),
            )
        else:
            mf = MemoryFile(
                path=path,
                character_id=character_id,
                target_id=target_id,
                title=title,
                content=content,
                summary=summary,
                tags=tags or [],
                importance=importance,
                source_event_id=source_event_id,
                memory_ids=memory_ids or [],
            )

        # 最终截断保护：确保任何路径都不超过字符上限（按条目截断，不切断单条记忆）
        if len(mf.content) > _MAX_MEMORY_FILE_CHARS:
            truncated = _truncate_entries(mf.content, path)
            mf = MemoryFile(
                path=mf.path,
                character_id=mf.character_id,
                target_id=mf.target_id,
                title=mf.title,
                content=truncated,
                summary=mf.summary,
                tags=mf.tags,
                importance=mf.importance,
                version=mf.version,
                source_event_id=mf.source_event_id,
                memory_ids=mf.memory_ids,
            )

        self._index[path] = mf
        self._save()
        _log.debug("[MemoryFS] write path=%s version=%d", path, mf.version)
        return mf

    def delete(self, path: str) -> bool:
        if path in self._index:
            del self._index[path]
            self._save()
            return True
        return False

    # ------------------------------------------------------------------
    # 路径辅助
    # ------------------------------------------------------------------

    def path_user(self, char_id: str, user_id: str) -> str:
        return f"characters/{char_id}/users/{user_id}.md"

    def path_user_persona(self, char_id: str, user_id: str) -> str:
        return f"characters/{char_id}/users/{user_id}/user_persona.md"

    def path_character_persona(self, char_id: str, user_id: str) -> str:
        return f"characters/{char_id}/users/{user_id}/character_persona.md"

    def path_recent_digest(self, char_id: str, user_id: str) -> str:
        return f"characters/{char_id}/users/{user_id}/recent_digest.md"

    def path_important_events(self, char_id: str, conversation_id: str) -> str:
        safe_conversation_id = conversation_id or "general"
        return f"characters/{char_id}/events/{safe_conversation_id}.md"

    def path_diary_daily(self, char_id: str) -> str:
        return f"characters/{char_id}/diary/daily.md"

    def path_diary_weekly(self, char_id: str) -> str:
        return f"characters/{char_id}/diary/weekly.md"

    def path_plot(self, char_id: str, conversation_id: str) -> str:
        return f"characters/{char_id}/plot/{conversation_id}.md"

    def path_world_events(self, char_id: str) -> str:
        return f"characters/{char_id}/world/events.md"

    def path_general(self, char_id: str) -> str:
        return f"characters/{char_id}/general.md"

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def list_for_character(self, char_id: str) -> list[MemoryFile]:
        """列出指定角色的所有逻辑文件，按 importance 降序。"""
        prefix = f"characters/{char_id}/"
        files = [mf for path, mf in self._index.items() if path.startswith(prefix)]
        return sorted(files, key=lambda m: m.importance, reverse=True)

    def read_user(self, char_id: str, user_id: str) -> MemoryFile | None:
        return self.read(self.path_user(char_id, user_id))

    def read_diary(self, char_id: str) -> MemoryFile | None:
        return self.read(self.path_diary_daily(char_id))

    def read_plot(self, char_id: str, conversation_id: str) -> MemoryFile | None:
        return self.read(self.path_plot(char_id, conversation_id))

    def build_prompt_context(
        self,
        char_id: str,
        user_id: str,
        conversation_id: str = "",
    ) -> str:
        """按结构化读取策略构建 prompt 注入文本（必读层）。

        必读：用户人格 + 角色关系理解 + 重要事件/剧情摘要 + 压缩近期摘要。
        旧版 raw daily 不再注入，避免把逐轮流水账塞进上下文。
        """
        parts: list[str] = []

        user_persona = self.read(self.path_user_persona(char_id, user_id))
        if user_persona:
            parts.append(user_persona.to_prompt_text())

        character_persona = self.read(self.path_character_persona(char_id, user_id))
        if character_persona:
            parts.append(character_persona.to_prompt_text())

        if conversation_id:
            event_mf = self.read(self.path_important_events(char_id, conversation_id))
            if event_mf:
                parts.append(event_mf.to_prompt_text())
            plot_mf = self.read_plot(char_id, conversation_id)
            if plot_mf:
                parts.append(plot_mf.to_prompt_text())

        digest_mf = self.read(self.path_recent_digest(char_id, user_id))
        if digest_mf:
            parts.append(digest_mf.to_prompt_text())

        return "\n\n".join(p for p in parts if p)

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not os.path.exists(self._index_file):
            self._index = {}
            return
        try:
            with open(self._index_file, encoding="utf-8") as f:
                raw = json.load(f)
            self._index = {k: MemoryFile.from_dict(v) for k, v in raw.items()}
            _log.debug("[MemoryFS] loaded %d entries from %s", len(self._index), self._index_file)
        except Exception as exc:
            _log.warning("[MemoryFS] load failed: %s", exc)
            self._index = {}

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._index_file), exist_ok=True)
            with open(self._index_file, "w", encoding="utf-8") as f:
                json.dump(
                    {k: v.to_dict() for k, v in self._index.items()},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as exc:
            _log.error("[MemoryFS] save failed: %s", exc)


def get_memory_fs(data_dir: str = _DEFAULT_DATA_DIR) -> MemoryFS:
    """获取全局 MemoryFS 单例。"""
    global _memory_fs
    if _memory_fs is None:
        _memory_fs = MemoryFS(data_dir=data_dir)
    return _memory_fs
