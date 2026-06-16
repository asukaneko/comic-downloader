"""
Hook Manager

Central coordinator for the Hook Runtime system.
Manages hook definitions, event dispatch, condition evaluation,
action execution, safety limits, and persistence.
"""

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Set

from nbot.hooks.actions import ActionExecutor
from nbot.hooks.conditions import ConditionEvaluator
from nbot.hooks.event_bus import ConversationEventBus, match_event_pattern
from nbot.hooks.models import (
    VALID_TRIGGER_MODES,
    ConversationHook,
    HookExecutionLog,
    RuntimeEvent,
)

_log = logging.getLogger(__name__)

_MAX_HOOKS_PER_TURN = 20
_MAX_EVENT_CHAIN_DEPTH = 5

_hook_manager = None


class HookManager:
    """Hook Runtime manager.

    Coordinates event bus, condition evaluator, and action executor.
    Provides hook CRUD, event emission, and persistence.
    """

    def __init__(self, data_dir: str = "data/web"):
        self._hooks: Dict[str, ConversationHook] = {}
        self._event_bus = ConversationEventBus()
        self._condition_evaluator = ConditionEvaluator()
        self._action_executor = ActionExecutor()
        self._execution_logs: List[HookExecutionLog] = []
        self._data_dir = os.path.abspath(data_dir)
        self._hooks_file = os.path.join(self._data_dir, "hooks.json")
        self._logs_file = os.path.join(self._data_dir, "hooks_logs.json")
        self._trigger_state_file = os.path.join(self._data_dir, "hooks_trigger_state.json")
        self._turn_hooks_executed: int = 0
        self._turn_hook_ids_executed: set = set()
        self._trigger_state: Dict[str, Set[str]] = {}
        self._event_notifier = None  # callback for frontend notifications
        self._load_hooks()
        self._load_logs()
        self._load_trigger_state()

    # -- Hook CRUD --

    def add_hook(self, hook: ConversationHook) -> ConversationHook:
        self._hooks[hook.id] = hook
        self._save_hooks()
        _log.info("[HookManager] added hook id=%s name=%s event=%s", hook.id, hook.name, hook.event)
        return hook

    def remove_hook(self, hook_id: str) -> bool:
        if hook_id not in self._hooks:
            return False
        del self._hooks[hook_id]
        self._trigger_state.pop(hook_id, None)
        self._save_hooks()
        self._save_trigger_state()
        _log.info("[HookManager] removed hook id=%s", hook_id)
        return True

    def get_hook(self, hook_id: str) -> Optional[ConversationHook]:
        return self._hooks.get(hook_id)

    def list_hooks(
        self, *, scope: str = "", event: str = "", enabled_only: bool = False
    ) -> List[ConversationHook]:
        result = list(self._hooks.values())
        if scope:
            result = [h for h in result if h.scope == scope]
        if event:
            result = [h for h in result if match_event_pattern(h.event, event)]
        if enabled_only:
            result = [h for h in result if h.enabled]
        result.sort(key=lambda h: h.priority)
        return result

    _UPDATABLE_FIELDS = frozenset({
        "name", "description", "enabled", "scope", "event", "priority",
        "conditions", "actions", "permissions", "timeout_ms", "max_retries",
        "trigger_mode", "character_id", "conversation_id", "user_id",
    })

    def update_hook(self, hook_id: str, **fields) -> bool:
        hook = self._hooks.get(hook_id)
        if hook is None:
            return False
        for key, value in fields.items():
            if key not in self._UPDATABLE_FIELDS:
                _log.warning("[HookManager] ignoring unknown field: %s", key)
                continue
            if key == "trigger_mode" and value not in VALID_TRIGGER_MODES:
                value = "always"
            setattr(hook, key, value)
        hook.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._save_hooks()
        return True

    def toggle_hook(self, hook_id: str, enabled: bool) -> bool:
        return self.update_hook(hook_id, enabled=enabled)

    def set_event_notifier(self, callback) -> None:
        """Set a callback invoked when a hook fires successfully.

        callback receives a dict: {hook_id, hook_name, event_type, conversation_id, status}
        """
        self._event_notifier = callback

    @staticmethod
    def _extract_display_message(hook: ConversationHook) -> str:
        for action in hook.actions:
            if not isinstance(action, dict):
                continue
            if action.get("type") == "log" and action.get("message"):
                return str(action.get("message"))
            if action.get("type") == "message" and action.get("content"):
                return str(action.get("content"))
        return hook.name

    def _notify_frontend(self, hook: ConversationHook, event: RuntimeEvent, log: HookExecutionLog) -> None:
        """Send hook trigger notification via callback if registered."""
        if not self._event_notifier:
            return
        try:
            self._event_notifier({
                "hook_id": hook.id,
                "hook_name": hook.name,
                "event_type": event.type,
                "conversation_id": event.conversation_id,
                "status": log.status,
                "display_message": self._extract_display_message(hook),
            })
        except Exception as e:
            _log.debug("[HookManager] notify frontend failed: %s", e)

    # -- Event Emission --

    async def emit_event(
        self,
        event: RuntimeEvent,
        *,
        context: Optional[Dict[str, Any]] = None,
        depth: int = 0,
    ) -> List[HookExecutionLog]:
        """Emit event, match hooks, evaluate conditions, execute actions."""
        if depth > _MAX_EVENT_CHAIN_DEPTH:
            return []

        await self._event_bus.emit(event)

        matched = self._match_hooks_for_event(event)
        if not matched:
            return []

        ctx = context or {}
        logs: List[HookExecutionLog] = []

        for hook in matched:
            if self._turn_hooks_executed >= _MAX_HOOKS_PER_TURN:
                _log.warning("[HookManager] per-turn limit reached")
                break
            if hook.id in self._turn_hook_ids_executed:
                continue
            if not self._condition_evaluator.evaluate(hook.conditions, event, ctx):
                continue
            if self._has_triggered_for_conversation(hook, event):
                continue
            log = await self._execute_hook(hook, event, ctx)
            logs.append(log)
            self._turn_hooks_executed += 1
            self._turn_hook_ids_executed.add(hook.id)

        return logs

    def reset_turn(self):
        """Reset per-turn counters. Call at the start of each turn."""
        self._turn_hooks_executed = 0
        self._turn_hook_ids_executed.clear()

    def _match_hooks_for_event(self, event: RuntimeEvent) -> List[ConversationHook]:
        matched = []
        for hook in self._hooks.values():
            if not hook.enabled:
                continue
            if not match_event_pattern(hook.event, event.type):
                continue
            if hook.scope == "character" and hook.character_id:
                if hook.character_id != event.character_id:
                    continue
            if hook.scope == "conversation" and hook.conversation_id:
                if hook.conversation_id != event.conversation_id:
                    continue
            if hook.scope == "user" and hook.user_id:
                if hook.user_id != event.user_id:
                    continue
            matched.append(hook)
        matched.sort(key=lambda h: h.priority)
        return matched

    async def _execute_hook(
        self, hook: ConversationHook, event: RuntimeEvent, ctx: Dict[str, Any]
    ) -> HookExecutionLog:
        # 权限检查
        if not self._check_permissions(hook, event):
            log = HookExecutionLog(
                hook_id=hook.id, event_id=event.id, status="denied",
                error="Permission denied",
                conversation_id=event.conversation_id,
                event_type=event.type,
            )
            self._append_log(log)
            return log

        max_attempts = 1 + max(0, hook.max_retries)
        last_log = None

        for attempt in range(max_attempts):
            last_log = await self._execute_hook_once(hook, event, ctx)
            if last_log.status == "success":
                break
            if attempt < max_attempts - 1:
                _log.debug(
                    "[HookManager] retry %d/%d for hook %s",
                    attempt + 1, hook.max_retries, hook.id,
                )

        self._append_log(last_log)
        if last_log.status in ("success", "partial"):
            self._mark_triggered_for_conversation(hook, event)
            self._notify_frontend(hook, event, last_log)
        return last_log

    async def _execute_hook_once(
        self, hook: ConversationHook, event: RuntimeEvent, ctx: Dict[str, Any]
    ) -> HookExecutionLog:
        start = time.time()
        try:
            timeout = hook.timeout_ms / 1000.0
            results = await asyncio.wait_for(
                self._action_executor.execute_all(hook.actions, event, ctx),
                timeout=timeout,
            )
            duration = int((time.time() - start) * 1000)
            executed = sum(1 for r in results if r.success)
            failed = [r for r in results if not r.success]
            return HookExecutionLog(
                hook_id=hook.id,
                event_id=event.id,
                status="success" if not failed else "partial",
                actions_executed=executed,
                error="; ".join(r.detail for r in failed) if failed else "",
                duration_ms=duration,
                conversation_id=event.conversation_id,
                event_type=event.type,
            )
        except asyncio.TimeoutError:
            duration = int((time.time() - start) * 1000)
            return HookExecutionLog(
                hook_id=hook.id, event_id=event.id, status="timeout",
                duration_ms=duration, error="Timeout",
                conversation_id=event.conversation_id,
                event_type=event.type,
            )
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            return HookExecutionLog(
                hook_id=hook.id, event_id=event.id, status="failed",
                duration_ms=duration, error=str(e),
                conversation_id=event.conversation_id,
                event_type=event.type,
            )

    def _has_triggered_for_conversation(
        self, hook: ConversationHook, event: RuntimeEvent
    ) -> bool:
        if hook.trigger_mode != "once_per_conversation":
            return False
        if not event.conversation_id:
            return False
        return event.conversation_id in self._trigger_state.get(hook.id, set())

    def _mark_triggered_for_conversation(
        self, hook: ConversationHook, event: RuntimeEvent
    ) -> None:
        if hook.trigger_mode != "once_per_conversation":
            return
        if not event.conversation_id:
            return
        seen = self._trigger_state.setdefault(hook.id, set())
        if event.conversation_id in seen:
            return
        seen.add(event.conversation_id)
        self._save_trigger_state()

    @staticmethod
    def _check_permissions(hook: ConversationHook, event: RuntimeEvent) -> bool:
        """检查 Hook 权限限制。

        permissions 示例：
            {"channels": ["web", "qq"]}       — 只允许特定频道
            {"deny_channels": ["telegram"]}    — 禁止特定频道
        """
        perms = hook.permissions
        if not perms:
            return True

        channel = event.payload.get("channel") or event.metadata.get("channel", "")

        # 允许列表
        allowed = perms.get("channels")
        if allowed and channel not in allowed:
            return False

        # 拒绝列表
        denied = perms.get("deny_channels")
        if denied and channel in denied:
            return False

        return True

    def _append_log(self, log: HookExecutionLog):
        self._execution_logs.append(log)
        if len(self._execution_logs) > 500:
            self._execution_logs = self._execution_logs[-250:]
        self._save_logs()

    # -- Persistence --

    def _save_hooks(self):
        try:
            data = [h.to_dict() for h in self._hooks.values()]
            os.makedirs(os.path.dirname(self._hooks_file), exist_ok=True)
            with open(self._hooks_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            _log.error("[HookManager] save failed: %s", e)

    def _load_hooks(self):
        try:
            if os.path.exists(self._hooks_file):
                with open(self._hooks_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data:
                    hook = ConversationHook.from_dict(item)
                    self._hooks[hook.id] = hook
                _log.info("[HookManager] loaded %d hooks", len(self._hooks))
        except Exception as e:
            _log.error("[HookManager] load failed: %s", e)

    def _save_logs(self):
        try:
            os.makedirs(os.path.dirname(self._logs_file), exist_ok=True)
            data = [l.to_dict() for l in self._execution_logs]
            with open(self._logs_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            _log.error("[HookManager] save logs failed: %s", e)

    def _load_logs(self):
        try:
            if os.path.exists(self._logs_file):
                with open(self._logs_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data:
                    self._execution_logs.append(HookExecutionLog.from_dict(item))
                _log.info("[HookManager] loaded %d execution logs", len(self._execution_logs))
        except Exception as e:
            _log.error("[HookManager] load logs failed: %s", e)

    def _save_trigger_state(self):
        try:
            os.makedirs(os.path.dirname(self._trigger_state_file), exist_ok=True)
            data = {hook_id: sorted(conversations) for hook_id, conversations in self._trigger_state.items()}
            with open(self._trigger_state_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            _log.error("[HookManager] save trigger state failed: %s", e)

    def _load_trigger_state(self):
        try:
            if os.path.exists(self._trigger_state_file):
                with open(self._trigger_state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._trigger_state = {
                    str(hook_id): {str(conv_id) for conv_id in conversation_ids}
                    for hook_id, conversation_ids in data.items()
                    if isinstance(conversation_ids, list)
                }
        except Exception as e:
            _log.error("[HookManager] load trigger state failed: %s", e)

    # -- Query --

    def get_execution_logs(
        self, *, hook_id: str = "", limit: int = 50
    ) -> List[Dict[str, Any]]:
        logs = self._execution_logs
        if hook_id:
            logs = [l for l in logs if l.hook_id == hook_id]
        result = logs[-limit:] if len(logs) > limit else logs
        return [l.to_dict() for l in reversed(result)]

    def get_stats(self) -> Dict[str, Any]:
        total = len(self._hooks)
        enabled = sum(1 for h in self._hooks.values() if h.enabled)
        return {
            "total_hooks": total,
            "enabled_hooks": enabled,
            "total_executions": len(self._execution_logs),
            "turn_hooks_executed": self._turn_hooks_executed,
            "event_bus": self._event_bus.get_stats(),
        }


def get_hook_manager(data_dir: str = "data/web") -> HookManager:
    global _hook_manager
    if _hook_manager is None:
        _hook_manager = HookManager(data_dir=data_dir)
    return _hook_manager
