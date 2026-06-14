"""群聊管理器 - CRUD + 持久化"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any

from nbot.group.models import GroupConversation, GroupConfig, InterCharacterRelation

_log = logging.getLogger(__name__)


def _get_data_path() -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base_dir, "data", "web", "groups.json")


class GroupManager:
    """群聊管理器（单例）"""

    _instance: GroupManager | None = None

    @classmethod
    def instance(cls) -> GroupManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, file_path: str | None = None):
        self._file_path = file_path or _get_data_path()
        self._lock = threading.Lock()
        self._groups: dict[str, GroupConversation] = {}
        self._channel_bindings: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._file_path):
                with open(self._file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for gid, gdata in (data.get("groups") or {}).items():
                    self._groups[gid] = GroupConversation.from_dict(gdata)
                self._channel_bindings = data.get("channel_bindings") or {}
                _log.info("loaded %d group conversations", len(self._groups))
        except Exception as e:
            _log.error("failed to load groups: %s", e)

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._file_path), exist_ok=True)
            data = {
                "groups": {gid: g.to_dict() for gid, g in self._groups.items()},
                "channel_bindings": dict(self._channel_bindings),
            }
            tmp = self._file_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._file_path)
        except Exception as e:
            _log.error("failed to save groups: %s", e)

    def create_group(
        self,
        name: str,
        character_ids: list[str],
        *,
        narrator_id: str | None = None,
        config: GroupConfig | None = None,
    ) -> GroupConversation:
        group = GroupConversation(
            name=name,
            character_ids=list(character_ids),
            narrator_id=narrator_id,
            config=config or GroupConfig(),
        )
        with self._lock:
            self._groups[group.group_id] = group
            self._save()
        _log.info("created group %s (%s)", group.group_id, name)
        return group

    def get_group(self, group_id: str) -> GroupConversation | None:
        return self._groups.get(group_id)

    def list_groups(self) -> list[GroupConversation]:
        return list(self._groups.values())

    def update_group(self, group_id: str, **kwargs: Any) -> GroupConversation | None:
        with self._lock:
            group = self._groups.get(group_id)
            if not group:
                return None
            if "name" in kwargs:
                group.name = kwargs["name"]
            if "config" in kwargs and isinstance(kwargs["config"], dict):
                group.config = GroupConfig.from_dict(kwargs["config"])
            if "narrator_id" in kwargs:
                group.narrator_id = kwargs["narrator_id"]
            group.updated_at = time.time()
            self._save()
        return group

    def delete_group(self, group_id: str) -> bool:
        with self._lock:
            if group_id not in self._groups:
                return False
            del self._groups[group_id]
            to_remove = [k for k, v in self._channel_bindings.items() if v == group_id]
            for k in to_remove:
                del self._channel_bindings[k]
            self._save()
        _log.info("deleted group %s", group_id)
        return True

    def add_character(self, group_id: str, character_id: str) -> bool:
        with self._lock:
            group = self._groups.get(group_id)
            if not group:
                return False
            if character_id not in group.character_ids:
                group.character_ids.append(character_id)
                group.updated_at = time.time()
                self._save()
            return True

    def remove_character(self, group_id: str, character_id: str) -> bool:
        with self._lock:
            group = self._groups.get(group_id)
            if not group:
                return False
            if character_id in group.character_ids:
                group.character_ids.remove(character_id)
                group.updated_at = time.time()
                self._save()
            return True

    def set_speaker_strategy(self, group_id: str, strategy: str) -> bool:
        valid = {"round_robin", "mention", "relevance", "random"}
        if strategy not in valid:
            _log.warning("invalid strategy: %s", strategy)
            return False
        with self._lock:
            group = self._groups.get(group_id)
            if not group:
                return False
            group.config.speaker_strategy = strategy
            group.updated_at = time.time()
            self._save()
        return True

    def bind_channel(self, group_id: str, channel_id: str) -> bool:
        with self._lock:
            if group_id not in self._groups:
                return False
            self._channel_bindings[channel_id] = group_id
            self._groups[group_id].bound_channel = channel_id
            self._save()
        _log.info("bound group %s to channel %s", group_id, channel_id)
        return True

    def unbind_channel(self, channel_id: str) -> bool:
        with self._lock:
            if channel_id not in self._channel_bindings:
                return False
            group_id = self._channel_bindings.pop(channel_id)
            if group_id in self._groups:
                self._groups[group_id].bound_channel = ""
            self._save()
        return True

    def get_group_by_channel(self, channel_id: str) -> GroupConversation | None:
        gid = self._channel_bindings.get(channel_id)
        if gid:
            return self._groups.get(gid)
        return None

    def update_relation(
        self,
        group_id: str,
        char_a: str,
        char_b: str,
        dimension: str,
        delta: float,
        reason: str = "",
    ) -> bool:
        with self._lock:
            group = self._groups.get(group_id)
            if not group:
                return False
            relation = group.get_relation(char_a, char_b)
            if not relation:
                relation = InterCharacterRelation(char_a=char_a, char_b=char_b)
                group.set_relation(relation)
            relation.update(dimension, delta, reason)
            group.updated_at = time.time()
            self._save()
        return True


# 便捷获取函数
def get_group_manager(file_path: str | None = None) -> GroupManager:
    """获取群聊管理器单例"""
    return GroupManager.instance()
