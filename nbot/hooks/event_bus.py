"""
对话事件总线

面向对话生命周期的事件总线，独立于 Gateway EventBus。
支持事件发射、订阅、历史查询。
"""

import asyncio
import logging
from collections import deque
from collections.abc import Callable, Coroutine
from enum import Enum
from typing import Any, Dict, List, Optional

from nbot.hooks.models import RuntimeEvent

_log = logging.getLogger(__name__)


# 文档事件名 → 代码实际事件名 的别名映射
# 用户在 Hook 里写文档名，也能匹配到代码实际 emit 的事件
_EVENT_ALIASES: Dict[str, List[str]] = {
    "pipeline.before_model_call": ["model.before_call"],
    "pipeline.after_model_call": ["model.after_call"],
    "pipeline.before_reply_send": ["reply.before_send"],
    "pipeline.after_reply_send": ["reply.after_send"],
    "pipeline.before_prompt_render": ["prompt.before_render"],
    "pipeline.after_prompt_render": ["prompt.after_render"],
    "pipeline.stream_chunk": ["model.on_stream_chunk"],
    "character.before_turn.after_memory_retrieve": ["character.after_memory_retrieve"],
    "character.before_turn.after_world_book_match": ["character.after_world_book_match"],
    "character.before_turn.after_reaction_plan": ["character.after_reaction_plan"],
    "character.after_turn.after_state_update": ["character.after_state_update"],
}


def match_event_pattern(pattern: str, event_type: str) -> bool:
    """Match event type against pattern with wildcard support."""
    if pattern == "*":
        return True
    if pattern.endswith(".*"):
        prefix = pattern[:-2]
        return event_type.startswith(prefix + ".")
    # 直接匹配
    if pattern == event_type:
        return True
    # 别名匹配：用户写的文档名 → 代码实际事件名
    aliases = _EVENT_ALIASES.get(pattern, [])
    return event_type in aliases


class HookEventType(str, Enum):
    """对话生命周期事件类型"""

    # 对话入口
    CONVERSATION_BEFORE_RECEIVE = "conversation.before_receive"

    # Pipeline 阶段
    PIPELINE_BEFORE_ATTACHMENTS = "pipeline.before_attachments"
    PIPELINE_AFTER_ATTACHMENTS = "pipeline.after_attachments"
    PIPELINE_BEFORE_KNOWLEDGE = "pipeline.before_knowledge"
    PIPELINE_AFTER_KNOWLEDGE = "pipeline.after_knowledge"

    # 角色运行时 - before_turn
    CHARACTER_BEFORE_TURN_STARTED = "character.before_turn.started"
    CHARACTER_AFTER_PROFILE_LOAD = "character.after_profile_load"
    CHARACTER_AFTER_MEMORY_RETRIEVE = "character.after_memory_retrieve"
    CHARACTER_AFTER_WORLD_BOOK_MATCH = "character.after_world_book_match"
    CHARACTER_AFTER_REACTION_PLAN = "character.after_reaction_plan"
    CHARACTER_BEFORE_TURN_FINISHED = "character.before_turn.finished"

    # Prompt 渲染
    PROMPT_BEFORE_RENDER = "prompt.before_render"
    PROMPT_AFTER_RENDER = "prompt.after_render"

    # 模型调用
    MODEL_BEFORE_CALL = "model.before_call"
    MODEL_ON_STREAM_CHUNK = "model.on_stream_chunk"
    MODEL_AFTER_CALL = "model.after_call"

    # 回复发送
    REPLY_BEFORE_SEND = "reply.before_send"
    REPLY_AFTER_SEND = "reply.after_send"

    # 角色运行时 - after_turn
    CHARACTER_AFTER_TURN_STARTED = "character.after_turn.started"
    CHARACTER_AFTER_STATE_UPDATE = "character.after_state_update"
    CHARACTER_AFTER_TURN_FINISHED = "character.after_turn.finished"

    # 记忆
    MEMORY_AFTER_EXTRACT = "memory.after_extract"

    # 状态变化
    STATE_CHANGED = "state.changed"
    RELATIONSHIP_CHANGED = "relationship.changed"

    # 工具调用
    TOOL_BEFORE_CALL = "tool.before_call"
    TOOL_AFTER_CALL = "tool.after_call"


class _Subscriber:
    """订阅者包装"""

    def __init__(
        self,
        callback: Callable[[RuntimeEvent], Any],
        *,
        name: str = "",
        once: bool = False,
    ):
        self.callback = callback
        self.name = name or getattr(callback, "__name__", "anonymous")
        self.once = once
        self.call_count = 0


class ConversationEventBus:
    """对话级事件总线

    独立于 Gateway 的 EventBus，专注于对话生命周期事件。
    """

    def __init__(self, *, history_max: int = 200):
        self._subscribers: Dict[str, List[_Subscriber]] = {}
        self._history: deque = deque(maxlen=history_max)
        self._history_max = history_max
        self._total_published = 0
        self._total_delivered = 0

    async def emit(self, event: RuntimeEvent) -> int:
        """发射事件，返回成功投递的订阅者数量"""
        self._history.append(event)
        self._total_published += 1

        matched = self._match_subscribers(event.type)
        if not matched:
            _log.debug("[HookEventBus] 无订阅者 event=%s", event.type)
            return 0

        delivered = 0
        to_remove: List[tuple[str, _Subscriber]] = []

        for sub in matched:
            try:
                result = sub.callback(event)
                if asyncio.iscoroutine(result):
                    await result
                sub.call_count += 1
                delivered += 1
                self._total_delivered += 1
                if sub.once:
                    to_remove.append((event.type, sub))
            except Exception as e:
                _log.error(
                    "[HookEventBus] 订阅者回调异常 event=%s sub=%s error=%s",
                    event.type,
                    sub.name,
                    str(e),
                )

        for topic, sub in to_remove:
            self.unsubscribe(topic, sub)

        return delivered

    def subscribe(
        self,
        event_pattern: str,
        callback: Callable[[RuntimeEvent], Any],
        *,
        name: str = "",
        once: bool = False,
    ) -> _Subscriber:
        """订阅事件类型，支持通配符（如 "character.*"）"""
        sub = _Subscriber(callback, name=name, once=once)
        if event_pattern not in self._subscribers:
            self._subscribers[event_pattern] = []
        self._subscribers[event_pattern].append(sub)
        _log.debug("[HookEventBus] 新订阅 pattern=%s sub=%s", event_pattern, sub.name)
        return sub

    def unsubscribe(self, event_pattern: str, subscriber: Optional[_Subscriber] = None) -> bool:
        """取消订阅"""
        if event_pattern not in self._subscribers:
            return False
        if subscriber is None:
            del self._subscribers[event_pattern]
            return True
        try:
            self._subscribers[event_pattern].remove(subscriber)
            if not self._subscribers[event_pattern]:
                del self._subscribers[event_pattern]
            return True
        except ValueError:
            return False

    def _match_subscribers(self, event_type: str) -> List[_Subscriber]:
        matched: List[_Subscriber] = []
        for pattern, subs in self._subscribers.items():
            if self._match_pattern(pattern, event_type):
                matched.extend(subs)
        return matched

    @staticmethod
    def _match_pattern(pattern: str, event_type: str) -> bool:
        if pattern == "*":
            return True
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            return event_type.startswith(prefix + ".")
        return pattern == event_type

    def get_history(
        self,
        *,
        event_type: str = "",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """查询事件历史"""
        events = self._history
        if event_type:
            events = [e for e in events if e.type == event_type]
        result = events[-limit:] if len(events) > limit else events
        return [e.to_dict() for e in reversed(result)]

    def get_stats(self) -> Dict[str, Any]:
        total_subs = sum(len(s) for s in self._subscribers.values())
        return {
            "patterns_registered": len(self._subscribers),
            "total_subscribers": total_subs,
            "total_published": self._total_published,
            "total_delivered": self._total_delivered,
            "history_size": len(self._history),
            "history_max": self._history_max,
            "patterns": list(self._subscribers.keys()),
        }

    def clear_history(self) -> None:
        self._history.clear()
