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
from typing import Any, Dict, List, Optional

from nbot.hooks.actions import ActionExecutor
from nbot.hooks.conditions import ConditionEvaluator
from nbot.hooks.event_bus import ConversationEventBus, match_event_pattern
from nbot.hooks.models import ConversationHook, HookExecutionLog, RuntimeEvent

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
        self._data_dir = data_dir
        self._hooks_file = os.path.join(data_dir, "hooks.json")
        self._turn_hooks_executed: int = 0
        self._turn_hook_ids_executed: set = set()
        self._load_hooks()

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
        self._save_hooks()
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
        "character_id", "conversation_id", "user_id",
    })

    def update_hook(self, hook_id: str, **fields) -> bool:
        hook = self._hooks.get(hook_id)
        if hook is None:
            return False
        for key, value in fields.items():
            if key not in self._UPDATABLE_FIELDS:
                _log.warning("[HookManager] ignoring unknown field: %s", key)
                continue
            setattr(hook, key, value)
        hook.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._save_hooks()
        return True

    def toggle_hook(self, hook_id: str, enabled: bool) -> bool:
        return self.update_hook(hook_id, enabled=enabled)

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
            log = HookExecutionLog(
                hook_id=hook.id,
                event_id=event.id,
                status="success" if not failed else "partial",
                actions_executed=executed,
                error="; ".join(r.detail for r in failed) if failed else "",
                duration_ms=duration,
            )
        except asyncio.TimeoutError:
            duration = int((time.time() - start) * 1000)
            log = HookExecutionLog(
                hook_id=hook.id, event_id=event.id, status="timeout",
                duration_ms=duration, error="Timeout",
            )
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            log = HookExecutionLog(
                hook_id=hook.id, event_id=event.id, status="failed",
                duration_ms=duration, error=str(e),
            )

        self._execution_logs.append(log)
        if len(self._execution_logs) > 500:
            self._execution_logs = self._execution_logs[-250:]
        return log

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
