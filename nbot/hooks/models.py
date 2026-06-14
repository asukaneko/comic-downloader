"""
Hook Runtime 数据模型

定义运行时事件、Hook 定义、执行日志等数据结构。
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _new_id(prefix: str = "hook") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RuntimeEvent:
    """运行时事件，由 Pipeline / CharacterRuntime 在关键节点发射"""

    type: str  # 事件类型，如 "character.before_turn.finished"
    source: str = ""  # 产生事件的模块标识
    conversation_id: str = ""
    character_id: str = ""
    user_id: str = ""
    group_id: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # 自动生成字段
    id: str = ""
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = _new_id("evt")
        if not self.created_at:
            self.created_at = _now_iso()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "source": self.source,
            "conversation_id": self.conversation_id,
            "character_id": self.character_id,
            "user_id": self.user_id,
            "group_id": self.group_id,
            "payload": self.payload,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RuntimeEvent":
        return cls(
            type=data.get("type", ""),
            source=data.get("source", ""),
            conversation_id=data.get("conversation_id", ""),
            character_id=data.get("character_id", ""),
            user_id=data.get("user_id", ""),
            group_id=data.get("group_id", ""),
            payload=data.get("payload", {}),
            metadata=data.get("metadata", {}),
            id=data.get("id", ""),
            created_at=data.get("created_at", ""),
        )


@dataclass
class ConversationHook:
    """Hook 定义，监听特定事件并执行动作"""

    name: str
    event: str  # 监听的事件类型（支持通配符，如 "character.*"）
    actions: List[Dict[str, Any]] = field(default_factory=list)

    # 可选字段
    id: str = ""
    description: str = ""
    enabled: bool = True
    scope: str = "global"  # global / character / conversation / user
    priority: int = 100  # 越小越先执行
    conditions: Dict[str, Any] = field(default_factory=dict)
    permissions: Dict[str, Any] = field(default_factory=dict)
    timeout_ms: int = 3000
    max_retries: int = 0

    # 关联
    character_id: str = ""  # scope=character 时绑定的角色 ID
    conversation_id: str = ""  # scope=conversation 时绑定的会话 ID
    user_id: str = ""  # scope=user 时绑定的用户 ID

    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = _new_id("hk")
        if not self.created_at:
            self.created_at = _now_iso()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "scope": self.scope,
            "event": self.event,
            "priority": self.priority,
            "conditions": self.conditions,
            "actions": self.actions,
            "permissions": self.permissions,
            "timeout_ms": self.timeout_ms,
            "max_retries": self.max_retries,
            "character_id": self.character_id,
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationHook":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            enabled=data.get("enabled", True),
            scope=data.get("scope", "global"),
            event=data.get("event", ""),
            priority=data.get("priority", 100),
            conditions=data.get("conditions", {}),
            actions=data.get("actions", []),
            permissions=data.get("permissions", {}),
            timeout_ms=data.get("timeout_ms", 3000),
            max_retries=data.get("max_retries", 0),
            character_id=data.get("character_id", ""),
            conversation_id=data.get("conversation_id", ""),
            user_id=data.get("user_id", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


@dataclass
class HookExecutionLog:
    """Hook 执行日志"""

    hook_id: str
    event_id: str
    status: str  # success / failed / skipped / timeout
    actions_executed: int = 0
    error: str = ""
    duration_ms: int = 0

    id: str = ""
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = _new_id("log")
        if not self.created_at:
            self.created_at = _now_iso()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "hook_id": self.hook_id,
            "event_id": self.event_id,
            "status": self.status,
            "actions_executed": self.actions_executed,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HookExecutionLog":
        return cls(
            id=data.get("id", ""),
            hook_id=data.get("hook_id", ""),
            event_id=data.get("event_id", ""),
            status=data.get("status", ""),
            actions_executed=data.get("actions_executed", 0),
            error=data.get("error", ""),
            duration_ms=data.get("duration_ms", 0),
            created_at=data.get("created_at", ""),
        )
