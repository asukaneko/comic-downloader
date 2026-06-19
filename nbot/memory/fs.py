"""
MemoryFS — 记忆逻辑文件系统

作为现有 PromptManager 记忆系统的上层组织层。
不替换底层存储，通过 path 字段把记忆条目组织成角色可读的逻辑视图。

存储：data/web/memory_fs.json（path → MemoryFile 的索引）
底层写入：仍通过 PromptManager.add_memory() 完成
"""

from __future__ import annotations

import json
import logging
import os
from typing import Dict, List, Optional

from nbot.memory.models import MemoryFile

_log = logging.getLogger(__name__)

_DEFAULT_DATA_DIR = "data/web"
_FS_INDEX_FILE = "memory_fs.json"

# 全局单例
_memory_fs: Optional[MemoryFS] = None


class MemoryFS:
    """记忆逻辑文件系统

    路径规范：
        characters/{char_id}/general.md           角色通用信息
        characters/{char_id}/users/{user_id}.md   对特定用户的关系摘要
        characters/{char_id}/diary/daily.md        最近日常日记
        characters/{char_id}/diary/weekly.md       本周摘要
        characters/{char_id}/plot/{conv_id}.md    剧情摘要
        characters/{char_id}/world/events.md       世界事件记录
    """

    def __init__(self, data_dir: str = _DEFAULT_DATA_DIR):
        self._index_file = os.path.join(data_dir, _FS_INDEX_FILE)
        self._index: Dict[str, MemoryFile] = {}
        self._load()

    # ------------------------------------------------------------------
    # 核心接口
    # ------------------------------------------------------------------

    def read(self, path: str) -> Optional[MemoryFile]:
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
        tags: Optional[List[str]] = None,
        importance: float = 0.0,
        source_event_id: str = "",
        memory_ids: Optional[List[str]] = None,
        append: bool = False,
    ) -> MemoryFile:
        """写入或更新逻辑路径的记忆文件。

        append=True 时将 content 追加到现有内容末尾（用于日记）。
        """
        existing = self._index.get(path)

        if existing and append:
            new_content = existing.content + "\n\n" + content if existing.content else content
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

    def list_for_character(self, char_id: str) -> List[MemoryFile]:
        """列出指定角色的所有逻辑文件，按 importance 降序。"""
        prefix = f"characters/{char_id}/"
        files = [mf for path, mf in self._index.items() if path.startswith(prefix)]
        return sorted(files, key=lambda m: m.importance, reverse=True)

    def read_user(self, char_id: str, user_id: str) -> Optional[MemoryFile]:
        return self.read(self.path_user(char_id, user_id))

    def read_diary(self, char_id: str) -> Optional[MemoryFile]:
        return self.read(self.path_diary_daily(char_id))

    def read_plot(self, char_id: str, conversation_id: str) -> Optional[MemoryFile]:
        return self.read(self.path_plot(char_id, conversation_id))

    def build_prompt_context(
        self,
        char_id: str,
        user_id: str,
        conversation_id: str = "",
    ) -> str:
        """按三层读取策略构建 prompt 注入文本（必读层）。

        必读：用户关系摘要 + 当前剧情摘要 + 最近日记摘要
        """
        parts: List[str] = []

        user_mf = self.read_user(char_id, user_id)
        if user_mf:
            parts.append(user_mf.to_prompt_text())

        if conversation_id:
            plot_mf = self.read_plot(char_id, conversation_id)
            if plot_mf:
                parts.append(plot_mf.to_prompt_text())

        diary_mf = self.read_diary(char_id)
        if diary_mf:
            parts.append(diary_mf.to_prompt_text())

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
