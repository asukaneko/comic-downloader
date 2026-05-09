"""
JSON 文件存储实现

第一阶段使用 JSON 文件存储角色状态和关系数据，
与项目现有存储风格一致，便于调试。
后续可迁移到 SQLite（通过 repository 接口切换）。
"""

import json
import logging
import os
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

_log = logging.getLogger(__name__)


class JsonStore:
    """通用 JSON 文件存储，带线程安全读写"""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self._lock = threading.Lock()
        self._cache: Optional[Dict[str, Any]] = None

    def _load(self) -> Dict[str, Any]:
        """从文件加载数据"""
        if self._cache is not None:
            return self._cache

        if not os.path.exists(self.file_path):
            return {}

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._cache = data if isinstance(data, dict) else {}
            return self._cache
        except Exception as exc:
            _log.warning("[JsonStore] 加载失败 %s: %s", self.file_path, exc)
            return {}

    def _save(self, data: Dict[str, Any]) -> None:
        """保存数据到文件"""
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._cache = data
        except Exception as exc:
            _log.error("[JsonStore] 保存失败 %s: %s", self.file_path, exc)

    def get(self, key: str) -> Optional[Any]:
        """获取指定 key 的数据"""
        with self._lock:
            data = self._load()
            return data.get(key)

    def set(self, key: str, value: Any) -> None:
        """设置指定 key 的数据"""
        with self._lock:
            data = self._load()
            data[key] = value
            self._save(data)

    def delete(self, key: str) -> bool:
        """删除指定 key 的数据"""
        with self._lock:
            data = self._load()
            if key in data:
                del data[key]
                self._save(data)
                return True
            return False

    def list_all(self) -> Dict[str, Any]:
        """返回所有数据"""
        with self._lock:
            return dict(self._load())

    def invalidate(self) -> None:
        """清除缓存，下次访问重新从文件加载"""
        with self._lock:
            self._cache = None


class CharacterStateJsonStore:
    """角色运行时状态的 JSON 存储"""

    def __init__(self, base_dir: str):
        self._store = JsonStore(os.path.join(base_dir, "data", "character", "states.json"))

    def get(self, character_id: str, scope_id: str) -> Optional[Dict[str, Any]]:
        """获取角色状态"""
        key = f"{character_id}::{scope_id}"
        return self._store.get(key)

    def save(self, character_id: str, scope_id: str, state_data: Dict[str, Any]) -> None:
        """保存角色状态"""
        key = f"{character_id}::{scope_id}"
        state_data["character_id"] = character_id
        state_data["scope_id"] = scope_id
        state_data["updated_at"] = datetime.now().isoformat()
        self._store.set(key, state_data)

    def delete(self, character_id: str, scope_id: str) -> bool:
        """删除角色状态"""
        key = f"{character_id}::{scope_id}"
        return self._store.delete(key)

    def list_by_character(self, character_id: str) -> List[Dict[str, Any]]:
        """列出指定角色的所有状态"""
        all_data = self._store.list_all()
        prefix = f"{character_id}::"
        return [v for k, v in all_data.items() if k.startswith(prefix)]


class RelationshipJsonStore:
    """关系状态的 JSON 存储"""

    def __init__(self, base_dir: str):
        self._store = JsonStore(os.path.join(base_dir, "data", "character", "relationships.json"))

    def get(self, character_id: str, target_id: str) -> Optional[Dict[str, Any]]:
        """获取关系状态"""
        key = f"{character_id}::{target_id}"
        return self._store.get(key)

    def save(self, character_id: str, target_id: str, rel_data: Dict[str, Any]) -> None:
        """保存关系状态"""
        key = f"{character_id}::{target_id}"
        rel_data["character_id"] = character_id
        rel_data["target_id"] = target_id
        rel_data["updated_at"] = datetime.now().isoformat()
        self._store.set(key, rel_data)

    def delete(self, character_id: str, target_id: str) -> bool:
        """删除关系状态"""
        key = f"{character_id}::{target_id}"
        return self._store.delete(key)

    def list_by_character(self, character_id: str) -> List[Dict[str, Any]]:
        """列出指定角色的所有关系"""
        all_data = self._store.list_all()
        prefix = f"{character_id}::"
        return [v for k, v in all_data.items() if k.startswith(prefix)]


class ProfileJsonStore:
    """角色卡的 JSON 存储"""

    def __init__(self, base_dir: str):
        self._store = JsonStore(os.path.join(base_dir, "data", "character", "profiles.json"))

    def get(self, character_id: str) -> Optional[Dict[str, Any]]:
        """获取角色卡"""
        return self._store.get(character_id)

    def save(self, character_id: str, profile_data: Dict[str, Any]) -> None:
        """保存角色卡"""
        profile_data["id"] = character_id
        self._store.set(character_id, profile_data)

    def delete(self, character_id: str) -> bool:
        """删除角色卡"""
        return self._store.delete(character_id)

    def list_all(self) -> List[Dict[str, Any]]:
        """列出所有角色卡"""
        all_data = self._store.list_all()
        return list(all_data.values())


class EventJsonStore:
    """角色事件的 JSON 存储"""

    def __init__(self, base_dir: str):
        self._store = JsonStore(os.path.join(base_dir, "data", "character", "events.json"))

    def append(self, event_data: Dict[str, Any]) -> None:
        """追加事件"""
        events = self._store.get("events") or []
        events.append(event_data)
        # 只保留最近 500 条事件
        if len(events) > 500:
            events = events[-500:]
        self._store.set("events", events)

    def list_recent(self, character_id: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        """列出最近的事件"""
        events = self._store.get("events") or []
        if character_id:
            events = [e for e in events if e.get("character_id") == character_id]
        return events[-limit:]

    def list_by_scope(self, scope_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """列出指定 scope 的事件"""
        events = self._store.get("events") or []
        events = [e for e in events if e.get("scope_id") == scope_id]
        return events[-limit:]


class DebugSnapshotJsonStore:
    """调试快照的 JSON 存储"""

    def __init__(self, base_dir: str):
        self._store = JsonStore(os.path.join(base_dir, "data", "character", "debug_snapshots.json"))

    def save_snapshot(self, scope_id: str, snapshot: Dict[str, Any]) -> None:
        """保存调试快照"""
        key = f"latest::{scope_id}"
        snapshot["saved_at"] = datetime.now().isoformat()
        self._store.set(key, snapshot)

    def get_latest(self, scope_id: str) -> Optional[Dict[str, Any]]:
        """获取最新的调试快照"""
        key = f"latest::{scope_id}"
        return self._store.get(key)
