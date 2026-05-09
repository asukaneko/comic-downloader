"""
角色事件系统

记录角色运行时中的关键事件，用于调试和后续的事件线功能。
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from nbot.character.storage.json_store import EventJsonStore, DebugSnapshotJsonStore

_log = logging.getLogger(__name__)


class CharacterEventLogger:
    """角色事件记录器"""

    def __init__(self, base_dir: str):
        self._event_store = EventJsonStore(base_dir)
        self._debug_store = DebugSnapshotJsonStore(base_dir)

    def log_event(
        self,
        character_id: str,
        target_id: str,
        scope_id: str,
        event_type: str,
        summary: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """记录角色事件"""
        event = {
            "id": str(uuid.uuid4()),
            "character_id": character_id,
            "target_id": target_id,
            "scope_id": scope_id,
            "event_type": event_type,
            "summary": summary,
            "payload": payload or {},
            "created_at": datetime.now().isoformat(),
        }
        self._event_store.append(event)

    def save_debug_snapshot(
        self,
        scope_id: str,
        *,
        prompt_injections: Optional[List[Dict[str, Any]]] = None,
        reaction_plan: Optional[Dict[str, Any]] = None,
        state_before: Optional[Dict[str, Any]] = None,
        state_after: Optional[Dict[str, Any]] = None,
        relationship_before: Optional[Dict[str, Any]] = None,
        relationship_after: Optional[Dict[str, Any]] = None,
        retrieved_memories: Optional[List[Dict[str, Any]]] = None,
        signals: Optional[Dict[str, Any]] = None,
    ) -> None:
        """保存调试快照"""
        snapshot = {
            "prompt_injections": prompt_injections or [],
            "reaction_plan": reaction_plan or {},
            "state_before": state_before or {},
            "state_after": state_after or {},
            "relationship_before": relationship_before or {},
            "relationship_after": relationship_after or {},
            "retrieved_memories": retrieved_memories or [],
            "signals": signals or {},
        }
        self._debug_store.save_snapshot(scope_id, snapshot)

    def get_latest_debug_snapshot(self, scope_id: str) -> Optional[Dict[str, Any]]:
        """获取最新的调试快照"""
        return self._debug_store.get_latest(scope_id)

    def get_recent_events(
        self, character_id: str = "", limit: int = 50
    ) -> List[Dict[str, Any]]:
        """获取最近的事件"""
        return self._event_store.list_recent(character_id, limit)
