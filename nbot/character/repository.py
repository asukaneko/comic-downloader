"""
角色数据仓库

通过 repository 接口访问存储层，业务逻辑不直接读写 JSON。
后续切换到 SQLite 只需更换 repository 实现。
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from nbot.character.models import (
    CharacterProfile,
    CharacterState,
    RelationshipState,
)
from nbot.character.storage.json_store import (
    CharacterStateJsonStore,
    ProfileJsonStore,
    RelationshipJsonStore,
)

_log = logging.getLogger(__name__)


class ProfileRepository:
    """角色卡仓库"""

    def __init__(self, base_dir: str):
        self._store = ProfileJsonStore(base_dir)

    def get(self, character_id: str) -> Optional[CharacterProfile]:
        """获取角色卡"""
        data = self._store.get(character_id)
        if not data:
            return None
        return CharacterProfile.from_personality_dict(data)

    def save(self, profile: CharacterProfile) -> None:
        """保存角色卡"""
        if not profile.id:
            profile.id = profile.name or "default"
        self._store.save(profile.id, profile.to_personality_dict())

    def delete(self, character_id: str) -> bool:
        """删除角色卡"""
        return self._store.delete(character_id)

    def list_all(self) -> List[CharacterProfile]:
        """列出所有角色卡"""
        return [
            CharacterProfile.from_personality_dict(d)
            for d in self._store.list_all()
        ]

    def get_or_create_by_personality(self, personality_data: Dict[str, Any]) -> CharacterProfile:
        """从旧 personality 数据获取或创建角色卡"""
        profile = CharacterProfile.from_personality_dict(personality_data)
        if not profile.id:
            profile.id = profile.name or "default"

        existing = self.get(profile.id)
        if existing:
            return existing

        self.save(profile)
        return profile


class CharacterStateRepository:
    """角色运行时状态仓库"""

    def __init__(self, base_dir: str):
        self._store = CharacterStateJsonStore(base_dir)

    def get(self, character_id: str, scope_id: str) -> Optional[CharacterState]:
        """获取角色状态"""
        data = self._store.get(character_id, scope_id)
        if not data:
            return None
        return CharacterState.from_dict(data)

    def get_or_create(
        self,
        character_id: str,
        scope_id: str,
        initial_state: Optional[Dict[str, Any]] = None,
    ) -> CharacterState:
        """获取或创建角色状态"""
        existing = self.get(character_id, scope_id)
        if existing:
            return existing

        # 从 initial_state 创建新状态
        state = CharacterState(
            character_id=character_id,
            scope_id=scope_id,
        )

        if initial_state:
            if "mood" in initial_state:
                state.mood = initial_state["mood"]
            if "affection" in initial_state:
                pass  # affection 已移到 RelationshipState
            if "energy" in initial_state:
                state.energy = initial_state["energy"]

        self.save(state)
        return state

    def save(self, state: CharacterState) -> None:
        """保存角色状态"""
        self._store.save(
            state.character_id,
            state.scope_id,
            state.to_dict(),
        )

    def delete(self, character_id: str, scope_id: str) -> bool:
        """删除角色状态"""
        return self._store.delete(character_id, scope_id)

    def list_by_character(self, character_id: str) -> List[CharacterState]:
        """列出指定角色的所有状态"""
        return [
            CharacterState.from_dict(d)
            for d in self._store.list_by_character(character_id)
        ]


class RelationshipRepository:
    """关系状态仓库"""

    def __init__(self, base_dir: str):
        self._store = RelationshipJsonStore(base_dir)

    def get(self, character_id: str, target_id: str) -> Optional[RelationshipState]:
        """获取关系状态"""
        data = self._store.get(character_id, target_id)
        if not data:
            return None
        return RelationshipState.from_dict(data)

    def get_or_create(
        self,
        character_id: str,
        target_id: str,
    ) -> RelationshipState:
        """获取或创建关系状态"""
        existing = self.get(character_id, target_id)
        if existing:
            return existing

        rel = RelationshipState(
            character_id=character_id,
            target_id=target_id,
        )
        self.save(rel)
        return rel

    def save(self, relationship: RelationshipState) -> None:
        """保存关系状态"""
        self._store.save(
            relationship.character_id,
            relationship.target_id,
            relationship.to_dict(),
        )

    def delete(self, character_id: str, target_id: str) -> bool:
        """删除关系状态"""
        return self._store.delete(character_id, target_id)

    def list_by_character(self, character_id: str) -> List[RelationshipState]:
        """列出指定角色的所有关系"""
        return [
            RelationshipState.from_dict(d)
            for d in self._store.list_by_character(character_id)
        ]
